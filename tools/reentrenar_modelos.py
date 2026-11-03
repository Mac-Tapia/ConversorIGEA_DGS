#!/usr/bin/env python
"""Orquesta o verifica el reentrenamiento integral sin ocultar etapas incompletas."""
from __future__ import annotations

import argparse
import json
import hashlib
import subprocess
import sys
import uuid
import os
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))


FAMILIAS_DE_ALGORITMO = {'gru': 'gru', 'nhits': 'gru', 'tft': 'gru', 'patchtst': 'gru',
                         'pinn_gnn': 'pinn', 'pinn': 'pinn', 'transformer': 'transformer',
                         'clasificador': 'clasificador', 'evolutivos': 'evolutivos',
                         'embeddings': 'embeddings', 'qlora': 'qlora'}


def _leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding='utf-8'))


def _estado(payload: dict, modelo: str) -> dict:
    if payload.get('status') in {'ERROR_ENTORNO', 'BLOQUEADO_POR_DATOS'}:
        return {'status': payload['status'], 'reason': payload.get('reason') or payload.get('error', '')}
    if payload.get('entrenado') is False:
        return {'status': 'BLOQUEADO_POR_DATOS', 'reason': payload.get('motivo') or payload.get('error', '')}
    if payload.get('status')=='RECHAZADO':
        return {'status':'RECHAZADO','reason':payload.get('reason',''),'result':payload}
    if 'promovido' in payload:
        return {'status': 'PROMOVIDO' if payload['promovido'] else 'RECHAZADO',
                'reason': '; '.join(payload.get('fallos') or ()), 'result': payload}
    # Embeddings y QLoRA conservan candidatos, pero no se presentan como activos sin su
    # evaluación funcional/reapertura. RECHAZADO aquí significa "promoción no aprobada".
    if payload.get('status') in {'CANDIDATO', 'EVALUADO'}:
        return {'status': 'RECHAZADO', 'reason': 'candidato conservado; promoción no aprobada',
                'candidate_status': payload.get('status'), 'result': payload}
    return {'status': 'ERROR_ENTORNO', 'reason': f'informe inesperado para {modelo}', 'result': payload}


def _subproceso(comando: list[str], reporte: Path, modelo: str, *, cwd: Path = REPO) -> dict:
    reporte.parent.mkdir(parents=True, exist_ok=True)
    log = reporte.with_suffix('.log')
    if reporte.exists():
        # Un proceso que termina sin escribir no puede heredar el éxito anterior.
        reporte.rename(reporte.with_name(f'{reporte.stem}.previous.{uuid.uuid4().hex}.json'))
    env=os.environ.copy();env.pop('CSG_GPU_PARENT_TOKEN',None)
    lock=Path(env.get('CSG_ML_GPU_LOCK') or str(Path(tempfile.gettempdir())/'convertersmartgrid-gpu.lock'))
    if lock.is_file():
        dueno=_leer(lock)
        if dueno.get('pid')==os.getpid():env['CSG_GPU_PARENT_TOKEN']=dueno['token']
    p = subprocess.run(comando, cwd=cwd, capture_output=True, text=True, check=False,env=env,
                       encoding='utf-8',errors='replace')
    log.write_text((p.stdout or '') + ('\n[stderr]\n' + p.stderr if p.stderr else ''), encoding='utf-8')
    if p.returncode != 0:
        if reporte.is_file():
            try:
                fallo=_leer(reporte)
                if fallo.get('status') in {'ERROR_ENTORNO','BLOQUEADO_POR_DATOS'}:
                    return {**_estado(fallo,modelo),'returncode':p.returncode,'training_completed':False,
                            'report':str(reporte),'log':str(log)}
            except (OSError,ValueError):pass
        return {'status': 'ERROR_ENTORNO', 'reason': f'código de salida {p.returncode}',
                'returncode': p.returncode, 'training_completed': False, 'log': str(log)}
    if not reporte.is_file():
        return {'status': 'ERROR_ENTORNO', 'reason': f'código {p.returncode} sin informe', 'log': str(log)}
    try:
        payload = _leer(reporte)
    except (OSError, ValueError) as exc:
        return {'status': 'ERROR_ENTORNO', 'reason': str(exc), 'log': str(log)}
    resultado = _estado(payload, modelo)
    # 043:RF-1, RF-5, RF-8: la decisión se liga a su candidato; la web no veía el del informe y lo daba por pendiente.
    resultado.update({k: payload[k] for k in ('candidate_id', 'modelo_registro', 'gates', 'version') if k in payload})
    if resultado['status'] == 'PROMOVIDO' and not payload.get('candidate_id'):
        # Sin candidato en el registro no hay puertas ni reapertura que lo respalden: nunca un OK falso.
        resultado.update(status='RECHAZADO', reason='el trabajador dijo promovido sin candidato en el registro común')
    resultado['training_completed'] = (payload.get('entrenado') is True
                                      or payload.get('training_completed') is True)
    resultado['evaluation_completed']=payload.get('evaluation_completed') is True
    resultado.update({'report': str(reporte), 'returncode': p.returncode, 'log': str(log)})
    return resultado


def orden_temporal(args, reporte: Path, algoritmo: str) -> list[str]:
    """046:RF-13: el candidato compite con las referencias y la GRU; nunca se sustituye por GRU."""
    cmd = [sys.executable, str(REPO / 'tools' / 'digital_twin_temporal_entrenar.py'),
           '--comparar', f'ingenuo,estacional_semanal,gru,{algoritmo}', '--libro', str(args.cabeceras),
           '--clase', args.clase_temporal, '--raiz', str(args.twin), '--output-json', str(reporte),
           '--semillas', args.semillas, '--cadencia-min', str(args.cadencia_temporal),
           '--zona-horaria', str(args.zona_horaria)]
    for par in args.pares_temporales or ():
        cmd += ['--par', par]
    for cliente in args.clientes_temporales or ():
        cmd += ['--cliente', cliente]
    return cmd


def _etapas(args, run_dir: Path):
    from convertersmartgrid.training_coordinator import TrainingStage

    py = sys.executable
    vocab = args.vocabulario
    dataset = args.dataset
    semillas = args.semillas

    def asistente(nombre: str, solo: str):
        reporte = run_dir / f'{nombre}.json'
        cmd = [py, str(REPO / 'tools' / 'asistente_entrenar.py'), '--output-json', str(reporte),
               '--solo', solo, '--dataset-v2', str(dataset), '--semillas', semillas]
        if vocab:
            cmd += ['--vocabulario', str(vocab)]
        return lambda: _subproceso(cmd, reporte, nombre)

    def gru():
        if not args.cabeceras:
            raise ValueError('indique --cabeceras con al menos 30 días observados')
        reporte = run_dir / 'gru.json'
        cmd = [py, str(REPO / 'tools' / 'digital_twin_temporal_entrenar.py'),
               '--cabeceras', str(args.cabeceras), '--raiz', str(args.twin),
               '--output-json', str(reporte), '--semillas', semillas]
        if args.zona_horaria:cmd+=['--zona-horaria',args.zona_horaria]
        if args.codigos_temporales:cmd+=['--codigos',args.codigos_temporales]
        for hoja in getattr(args,'hojas_temporales',[]):cmd+=['--hoja',hoja]
        for campo,flag in (('temporal_desde','--desde'),('temporal_hasta','--hasta')):
            if getattr(args,campo,None):cmd += [flag,getattr(args,campo)]
        return _subproceso(cmd, reporte, 'gru')

    def pinn():
        reporte = run_dir / 'pinn.json'
        cmd = [py, str(REPO / 'tools' / 'digital_twin_entrenar.py'), '--forzar',
               '--raiz', str(args.twin), '--output-json', str(reporte)]
        return _subproceso(cmd, reporte, 'pinn')

    def evolutivos():
        reporte = run_dir / 'evolutivos.json'
        cmd = [py, str(REPO / 'tools' / 'evaluar_evolutivos.py'), '--seeds', '30',
               '--report', str(reporte)]
        return _subproceso(cmd, reporte, 'evolutivos')

    def embeddings():
        destino = run_dir / 'embeddings'
        train_report = destino / 'decision.json'
        entrenado = _subproceso(
            [py, str(REPO / 'tools' / 'asistente_embeddings.py'), 'entrenar', '--dataset', str(dataset),
             '--destino', str(destino), '--modelo', args.embedding_model], train_report, 'embeddings')
        if entrenado['status'] in {'ERROR_ENTORNO','BLOQUEADO_POR_DATOS'}:
            return entrenado
        modelo = destino / 'modelo'
        eval_dir = run_dir / 'embeddings-eval'
        evaluado=_subproceso(
            [py, str(REPO / 'tools' / 'asistente_embeddings.py'), 'evaluar', '--dataset', str(dataset),
             '--destino', str(eval_dir), '--modelo', str(modelo)], eval_dir / 'decision.json', 'embeddings')
        evaluado['training_completed']=entrenado.get('training_completed',False)
        evaluado['training_report']=entrenado.get('report')
        return evaluado

    def qlora():
        if not args.llm_dataset:raise ValueError('indique --llm-dataset con el corpus generativo sellado; no se sustituye por dataset v2')
        destino, reporte = run_dir / 'qlora', run_dir / 'qlora' / 'training_manifest.json'
        cmd = [py, str(REPO / 'tools' / 'asistente_qlora.py'), 'entrenar', '--dataset', str(args.llm_dataset),
               '--salida', str(destino)]
        if args.qlora_model:cmd+=['--modelo',args.qlora_model]
        if args.qlora_revision:cmd+=['--revision',args.qlora_revision]
        return _subproceso(cmd, reporte, 'qlora')

    return [
        TrainingStage('transformer', asistente('transformer', 'ordenes')),
        TrainingStage('clasificador', asistente('clasificador', 'informes')),
        TrainingStage('gru', gru), TrainingStage('pinn', pinn),
        TrainingStage('evolutivos', evolutivos, uses_gpu=False),
        TrainingStage('embeddings', embeddings), TrainingStage('qlora', qlora),
    ]


def etapas_del_experimento(experimento, etapas: list, args, run_dir: Path) -> list:
    """La familia del contrato; cada resultado dice su algoritmo, sin crear etapas fuera de ``ORDEN_MODELOS``.

    046:RF-13: N-HiTS, TFT y PatchTST se ejecutan e informan dentro de la etapa ``gru``.
    """
    from convertersmartgrid.training_coordinator import TrainingStage

    familia = FAMILIAS_DE_ALGORITMO[experimento.algoritmo]
    elegidas = [etapa for etapa in etapas if etapa.name == familia]
    if experimento.algoritmo in {'nhits', 'tft', 'patchtst'}:
        reporte = run_dir / f'{experimento.algoritmo}.json'
        orden = orden_temporal(args, reporte, experimento.algoritmo)
        elegidas = [TrainingStage('gru', lambda: _subproceso(orden, reporte, 'gru'))]

    def con_algoritmo(etapa):
        return TrainingStage(etapa.name, lambda: {**etapa.run(), 'algorithm': experimento.algoritmo}, uses_gpu=etapa.uses_gpu)
    return [con_algoritmo(etapa) for etapa in elegidas]


def huella_entrada(ruta: Path, *, tipo: str) -> str:
    """043:RF-7: el contenido del búfer importa aunque no exista manifest.json."""
    ruta = Path(ruta)
    if ruta.is_file():
        with ruta.open('rb') as archivo:
            return hashlib.file_digest(archivo, 'sha256').hexdigest()
    if ruta.is_dir():
        archivos = ((ruta / 'objetos').rglob('*.json') if tipo == 'twin' else ruta.rglob('*'))
        entradas = []
        for archivo in sorted(p for p in archivos if p.is_file()):
            with archivo.open('rb') as contenido:
                digest = hashlib.file_digest(contenido, 'sha256').hexdigest()
            entradas.append((archivo.relative_to(ruta).as_posix(), digest))
        return hashlib.sha256(json.dumps(entradas, ensure_ascii=False).encode('utf-8')).hexdigest()
    return hashlib.sha256(b'entrada-ausente').hexdigest()


def verificar(reporte: Path, *, fail_on_incomplete: bool) -> int:
    if not reporte.is_file():
        print(json.dumps({'ok': False, 'reason': 'reporte ausente'}, ensure_ascii=False))
        return 2
    payload = _leer(reporte)
    permitidos = {'PROMOVIDO', 'RECHAZADO', 'BLOQUEADO_POR_DATOS', 'ERROR_ENTORNO'}
    etapas = payload.get('stages') or []
    from convertersmartgrid.training_coordinator import ORDEN_MODELOS
    estados_validos = (len(etapas) == len(ORDEN_MODELOS)
                       and {x.get('model') for x in etapas} == set(ORDEN_MODELOS)
                       and all(x.get('status') in permitidos for x in etapas))
    completo = bool(payload.get('complete')) and estados_validos
    todos_entrenados = completo and all(x.get('status') in {'PROMOVIDO', 'RECHAZADO'}
                                        and x.get('training_completed') is True for x in etapas)
    operaciones_completas=completo and all(x.get('status') in {'PROMOVIDO','RECHAZADO'} and
        (x.get('training_completed') is True or x.get('model')=='evolutivos' and x.get('evaluation_completed') is True)
        for x in etapas)
    ok = operaciones_completas if fail_on_incomplete else completo
    salida = {'ok': ok, 'complete': completo, 'all_trained': todos_entrenados,
              'all_required_operations_completed':operaciones_completas,
              'statuses': {x.get('model'): x.get('status') for x in etapas}}
    print(json.dumps(salida, ensure_ascii=False, indent=2))
    return 0 if ok else 2


def main(argv=None) -> int:
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.digital_twin.buffer import raiz_buffer

    p = argparse.ArgumentParser(description='Reentrenamiento integral reanudable')
    sub = p.add_subparsers(dest='accion')
    run = sub.add_parser('run')
    run.add_argument('--config', type=Path, help='Contrato ExperimentoSpec con contexto y política sellados')
    run.add_argument('--validar-config', action='store_true', help='Valida y muestra huella sin entrenar')
    run.add_argument('--run-dir', type=Path)
    run.add_argument('--report', type=Path)
    run.add_argument('--resume', action='store_true')
    run.add_argument('--dataset', type=Path, default=almacen.raiz() / 'dataset')
    run.add_argument('--vocabulario', type=Path, default=almacen.raiz() / 'vocabulario.json')
    run.add_argument('--twin', type=Path, default=raiz_buffer())
    run.add_argument('--cabeceras', type=Path)
    run.add_argument('--zona-horaria',help='Zona IANA explicita de las mediciones temporales')
    run.add_argument('--codigos-temporales',help='Codigos de columnas del libro ancho, separados por coma')
    run.add_argument('--hoja-temporal',dest='hojas_temporales',action='append',default=[],help='Hoja de medidor para la etapa GRU; repetible')
    run.add_argument('--temporal-desde',help='Inicio ISO inclusivo del alcance GRU')
    run.add_argument('--temporal-hasta',help='Fin ISO exclusivo del alcance GRU')
    run.add_argument('--clase-temporal',choices=('cabecera','cliente'),default='cabecera',help='Objetivos de N-HiTS, TFT o PatchTST')
    run.add_argument('--cadencia-temporal',type=int,help='Cadencia declarada de la medición para N-HiTS, TFT o PatchTST')
    run.add_argument('--par-temporal',dest='pares_temporales',action='append',default=[],help='alimentador=medidor; repetible')
    run.add_argument('--cliente-temporal',dest='clientes_temporales',action='append',default=[],help='Código de suministro; repetible')
    run.add_argument('--llm-dataset',type=Path,help='Corpus generativo sellado de 047 T7, distinto del dataset v2')
    run.add_argument('--semillas', default='11,23,37,53,71')
    run.add_argument('--embedding-model', default='intfloat/multilingual-e5-base')
    run.add_argument('--qlora-model',help='Base del catalogo; por defecto NF4 fijada de 047 T7')
    run.add_argument('--qlora-revision',help='Revision exacta del catalogo; no admite referencias mutables')
    verify = sub.add_parser('verify')
    verify.add_argument('--report', type=Path, required=True)
    verify.add_argument('--fail-on-incomplete', action='store_true')
    # Compatibilidad con el CLI inicial: --run-dir [--estado].
    p.add_argument('--run-dir', type=Path)
    p.add_argument('--estado', action='store_true')
    args = p.parse_args(argv)
    if args.accion == 'verify':
        return verificar(args.report, fail_on_incomplete=args.fail_on_incomplete)
    if args.accion is None and args.run_dir:
        reporte = args.run_dir / 'report.json'
        if args.estado:
            print(json.dumps(_leer(reporte) if reporte.is_file() else {'complete': False, 'stages': []},
                             ensure_ascii=False, indent=2))
            return 0
        p.error('use el subcomando run')
    if args.accion != 'run':
        p.error('indique run o verify')
    experimento = None
    familia = None
    if args.config:
        from convertersmartgrid.experimentos import cargar_experimento
        try:
            experimento = cargar_experimento(args.config)
        except (OSError, ValueError) as exc:
            p.error(str(exc))
        familia = FAMILIAS_DE_ALGORITMO.get(experimento.algoritmo)
        if familia is None:
            p.error(f'algoritmo no soportado: {experimento.algoritmo}')
        args.semillas = ','.join(str(s) for s in experimento.semillas)
        if args.validar_config:
            print(json.dumps({'schema_version': 1, 'config_hash': experimento.huella,
                              'etapas': [familia], 'algorithm': experimento.algoritmo}))
            return 0
    elif args.validar_config:
        p.error('--validar-config requiere --config')
    run_dir = args.run_dir or almacen.raiz() / 'training'
    from convertersmartgrid.asistente.ollama import liberar_gpu_para_entrenar
    from convertersmartgrid.training_coordinator import TrainingCoordinator
    etapas = _etapas(args, run_dir)
    if experimento:
        if experimento.algoritmo in {'nhits', 'tft', 'patchtst'} and not (
                args.cabeceras and args.zona_horaria and args.cadencia_temporal):
            p.error(f'{experimento.algoritmo} necesita --cabeceras, --zona-horaria y --cadencia-temporal')
        etapas = etapas_del_experimento(experimento, etapas, args, run_dir)
    entradas = {}
    for nombre in ('dataset', 'vocabulario', 'twin', 'cabeceras','llm_dataset'):
        ruta = getattr(args, nombre)
        if ruta is not None:
            fuente = Path(ruta)
            entradas[nombre] = {'path': str(fuente.resolve()),
                                'sha256': huella_entrada(fuente, tipo=nombre)}
    huella = hashlib.sha256(json.dumps({'experimento': experimento.huella if experimento else None,
        'entradas': entradas, 'semillas': args.semillas, 'embedding_model': args.embedding_model,
        'qlora_model': args.qlora_model, 'qlora_revision': args.qlora_revision,
        'zona_horaria':args.zona_horaria,'codigos_temporales':args.codigos_temporales,
        'alcance_temporal':{'hojas':args.hojas_temporales,'desde':args.temporal_desde,'hasta':args.temporal_hasta},
        'model_catalog_sha256':huella_entrada(REPO/'docs/MODELOS_IA_LOCK.json',tipo='catalogo')},
        sort_keys=True).encode()).hexdigest()
    try:
        informe = TrainingCoordinator(etapas, run_dir, config_hash=huella,
                                      liberar_ollama=liberar_gpu_para_entrenar).run(resume=args.resume)
    except ValueError as exc:
        # 043:RF-7: otra configuración no reutiliza nada; se dice y no se toca lo que había.
        print(json.dumps({'ok': False, 'reason': str(exc)}, ensure_ascii=False))
        return 2
    destino = args.report or run_dir / 'report.json'
    if destino != run_dir / 'report.json':
        from convertersmartgrid.trabajadores_ml import escribir_informe
        escribir_informe(destino, informe)                                      # 043:RF-13
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
