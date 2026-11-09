#!/usr/bin/env python
"""Ciclo común de aprendizaje (spec 050): congelar, ejecutar, ver el estado, cancelar y revertir.

Las etapas son las de ``tools/reentrenar_modelos.py``, pero leen las copias de la instantánea y no
el búfer ni el dataset vivos: así todas las familias aprenden de lo mismo.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))


def _raiz_defecto() -> Path:
    from convertersmartgrid.asistente import almacen
    return almacen.raiz() / 'aprendizaje'


def _pares(valores: list[str], que: str) -> dict[str, str]:
    salida = {}
    for v in valores or ():
        clave, sep, valor = v.partition('=')
        if not sep or not clave or not valor:
            raise SystemExit(f'{que} debe ser nombre=valor: {v}')
        salida[clave] = valor
    return salida


def _versiones() -> dict[str, str]:
    """Revisión del código y catálogo de modelos: un ciclo con otro código es otro ciclo."""
    rev = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO, capture_output=True, text=True, check=False)
    catalogo = REPO / 'docs' / 'MODELOS_IA_LOCK.json'
    return {'codigo': rev.stdout.strip() or 'sin-git',
            'catalogo_modelos': hashlib.sha256(catalogo.read_bytes()).hexdigest() if catalogo.is_file() else 'ausente'}


def _contexto(texto: str):
    ruta = Path(texto)
    if ruta.is_file():
        from convertersmartgrid.aprendizaje_continuo import (
            ESQUEMA_CONTEXTO_CICLO, ESQUEMA_CONTEXTO_DOCUMENTAL, ESQUEMA_CONTEXTO_MIXTO)
        dato = json.loads(ruta.read_text(encoding='utf-8'))
        if isinstance(dato, dict) and dato.get('schema') in (
                ESQUEMA_CONTEXTO_CICLO, ESQUEMA_CONTEXTO_DOCUMENTAL, ESQUEMA_CONTEXTO_MIXTO):
            return dato
        from convertersmartgrid.experimentos import cargar_experimento
        return cargar_experimento(ruta).contexto
    return texto


def _etapas(instantanea: dict, familias: list[str], args, run_dir: Path) -> list:
    """Las etapas de ``reentrenar_modelos``, con las rutas de la instantánea congelada."""
    from convertersmartgrid.aprendizaje_continuo import preparar_fuentes, ruta_de
    from convertersmartgrid.productores_aprendizaje import ProductoresReales
    preparar_fuentes(instantanea, familias, parametros={
        'zona_horaria': getattr(args, 'zona_horaria', None),
        'cadencia_min': getattr(args, 'cadencia_min', None),
        'horizontes': getattr(args, 'horizontes', None)},
        destino=run_dir.parent / 'preparacion.json', productores=ProductoresReales())
    spec = importlib.util.spec_from_file_location('reentrenar_modelos', REPO / 'tools' / 'reentrenar_modelos.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def copia(nombre):
        return ruta_de(instantanea, nombre) if nombre in instantanea['archivos'] else None
    ns = SimpleNamespace(
        dataset=copia('dataset'), vocabulario=copia('vocabulario'), twin=copia('twin'),
        cabeceras=copia('cabeceras'), llm_dataset=copia('llm_dataset'), semillas=args.semillas,
        zona_horaria=args.zona_horaria, codigos_temporales=None, hojas_temporales=[],
        temporal_desde=None, temporal_hasta=None, ablaciones=False, config=None,
        embedding_model=args.embedding_model, qlora_model=None, qlora_revision=None,
        instantanea=Path(instantanea['ruta']),
        ciclo_comun=True, publicar_individual=False, clase_temporal='cabecera',
        cadencia_temporal=getattr(args, 'cadencia_min', None),
        horizontes_temporales=getattr(args, 'horizontes', None), pares_temporales=[], clientes_temporales=[])
    return [e for e in mod._etapas(ns, run_dir) if e.name in familias]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Ciclo común de aprendizaje continuo (spec 050)')
    p.add_argument('--raiz', type=Path, help='Carpeta del aprendizaje; por defecto la del asistente')
    sub = p.add_subparsers(dest='accion', required=True)
    c = sub.add_parser('congelar', help='Copia verificada de las fuentes del ciclo (050:RF-1)')
    c.add_argument('--fuente', action='append', default=[], help='nombre=ruta; repetible')
    c.add_argument('--contexto', required=True, help='Huella SHA-256 del contexto 043, ExperimentoSpec o manifiesto de varios proyectos')
    c.add_argument('--version', action='append', default=[], help='nombre=valor añadido a las versiones')
    e = sub.add_parser('ciclo', help='Congela y ejecuta un ciclo único (050:RF-4); entrena en GPU')
    e.add_argument('--fuente', action='append', default=[])
    e.add_argument('--contexto', required=True)
    e.add_argument('--familias', required=True, help='Separadas por coma, de ORDEN_MODELOS')
    e.add_argument('--politica-hash', required=True, help='Huella de la política de evaluación (044)')
    e.add_argument('--tiempo-s', type=float, required=True)
    e.add_argument('--memoria-gib', type=float, required=True)
    e.add_argument('--sin-gpu', action='store_true')
    e.add_argument('--semillas', default='11,23,37,53,71')
    e.add_argument('--zona-horaria')
    e.add_argument('--cadencia-min', type=int, help='Cadencia declarada de las medidas para la etapa GRU')
    e.add_argument('--horizontes', help='Horizontes temporales en pasos, fijados antes del ciclo')
    e.add_argument('--embedding-model', default='intfloat/multilingual-e5-base')
    e.add_argument('--cancelar-archivo', type=Path, help='Solicitud cooperativa del trabajo de la cola')
    e.add_argument('--solo-preparar', action='store_true', help='Preflight CPU por familia; no crea trabajadores ni toma GPU')
    programado = sub.add_parser('plan', help='Ejecuta solo el plan declarativo explícito de la vigilancia')
    programado.add_argument('--archivo', type=Path, required=True)
    programado.add_argument('--plan-hash', required=True, help='SHA-256 del plan aprobado al encolarlo')
    programado.add_argument('--cancelar-archivo', type=Path)
    programado.add_argument('--solo-preparar', action='store_true', help='Solo preflight CPU del plan')
    sub.add_parser('estado', help='Fases del aprendizaje con versiones y motivos (050:RF-10)')
    k = sub.add_parser('cancelar', help='Cancela un ciclo en curso')
    k.add_argument('--clave', required=True)
    sub.add_parser('revertir', help='Vuelve al conjunto anterior, comprobado por relectura')
    args = p.parse_args(argv)

    from convertersmartgrid import aprendizaje_continuo as ac
    if args.accion == 'plan':
        # Antes de leer fuentes o tomar GPU: run_process ya puede cancelar cooperativamente.
        print('Preparando el ciclo conjunto desde su plan explícito.', flush=True)
        try:
            plan = ac.cargar_plan_ciclo(args.archivo)
            if plan['plan_hash'] != args.plan_hash:
                raise ac.CicloBloqueado('el plan cambió después de encolarlo; requiere una solicitud nueva')
            orden = ['--raiz', plan['raiz'], 'ciclo', '--contexto', plan['contexto'],
                '--familias', ','.join(plan['familias']), '--politica-hash', plan['politica_hash'],
                '--tiempo-s', str(plan['tiempo_s']), '--memoria-gib', str(plan['memoria_gib'])]
            for nombre, ruta in plan['fuentes'].items():
                orden += ['--fuente', f'{nombre}={ruta}']
            for nombre, valor in plan['parametros'].items():
                orden += ['--' + nombre.replace('_', '-'), str(valor)]
            if not plan['usa_gpu']:
                orden += ['--sin-gpu']
            if args.cancelar_archivo:
                orden += ['--cancelar-archivo', str(args.cancelar_archivo)]
            if args.solo_preparar:
                orden += ['--solo-preparar']
        except (OSError, ValueError) as exc:
            ac.registrar_bloqueo(_raiz_defecto(), 'cola', [str(exc)])
            print(json.dumps({'ok': False, 'estado': 'bloqueado', 'motivo': str(exc)}, ensure_ascii=False))
            return 2
        return main(orden)
    raiz = args.raiz or _raiz_defecto()
    try:
        if args.accion in ('congelar', 'ciclo'):
            fuentes = {n: Path(r) for n, r in _pares(args.fuente, '--fuente').items()}
            versiones = {**_versiones(), **_pares(getattr(args, 'version', []), '--version')}
            if args.accion == 'ciclo':
                parametros = {k: getattr(args, k) for k in (
                    'semillas', 'zona_horaria', 'cadencia_min', 'horizontes', 'embedding_model')}
                versiones['parametros_ciclo'] = ac.huella_parametros_ciclo(parametros)
            inst = ac.congelar_instantanea(fuentes, raiz, contexto=_contexto(args.contexto), versiones=versiones)
            if args.accion == 'congelar':
                salida = {'ok': True, 'snapshot_id': inst['snapshot_id'], 'ruta': inst['ruta']}
            else:
                from convertersmartgrid.asistente import almacen
                from convertersmartgrid.model_registry import RegistroModelo
                from convertersmartgrid.training_coordinator import _memoria_sistema
                familias = [f.strip() for f in args.familias.split(',') if f.strip()]
                from convertersmartgrid.productores_aprendizaje import ProductoresReales
                clave = ac.clave_ciclo(inst['snapshot_id'], familias, args.politica_hash)
                preparado = ac.preflight_ciclo(inst, familias, parametros={
                    'zona_horaria': args.zona_horaria, 'cadencia_min': args.cadencia_min,
                    'horizontes': args.horizontes}, destino=raiz / 'preflight' / f'{clave}.json',
                    productores=ProductoresReales())
                if args.solo_preparar:
                    print(json.dumps(preparado, ensure_ascii=False, indent=2))
                    return 0 if preparado['estado'] == 'preparado' else 2
                if preparado['estado'] != 'preparado':
                    raise ac.CicloBloqueado('; '.join(preparado['motivos']))
                etapas = _etapas(inst, familias, args, raiz / 'ciclos' / clave / 'etapas')
                faltan = sorted(set(familias) - {e.name for e in etapas})
                if faltan:
                    raise ac.CicloBloqueado(f'familias sin etapa: {faltan}')
                # El mismo registro común en que anotan sus candidatos los trabajadores (043:RF-1).
                registro = RegistroModelo(almacen.raiz() / 'model_registry')
                salida = ac.ejecutar_ciclo(
                    raiz, inst, etapas, politica_hash=args.politica_hash, registro=registro,
                    presupuesto=ac.Presupuesto(args.tiempo_s, args.memoria_gib, not args.sin_gpu),
                    memoria_libre_gib=lambda: _memoria_sistema()['fisica_gib'],
                    cancelado=lambda: bool(args.cancelar_archivo and args.cancelar_archivo.exists()))
        elif args.accion == 'estado':
            salida = ac.estado_aprendizaje(raiz)
        elif args.accion == 'cancelar':
            salida = {'solicitada': ac.cancelar_ciclo(raiz, args.clave)}
        else:
            salida = {'ok': True, 'conjunto': ac.revertir_conjunto(raiz)}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        ac.registrar_bloqueo(raiz, 'preparacion', [str(exc)])
        print(json.dumps({'ok': False, 'estado': 'bloqueado', 'motivo': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(salida, ensure_ascii=False, indent=2, default=str))
    return 0 if salida.get('estado') not in ('bloqueado',) else 2


if __name__ == '__main__':
    raise SystemExit(main())
