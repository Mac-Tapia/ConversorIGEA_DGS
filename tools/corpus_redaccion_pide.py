#!/usr/bin/env python
"""Revisión humana del corpus PIDE que enseña al asistente a redactar (spec 072, RF-19).

Lee los fragmentos de un corpus de ``pide_dataset`` (``fragments.jsonl``) y su registro de revisión
(``revision_redaccion.jsonl``, en la misma carpeta salvo ``--registro``). Lista lo pendiente, anota las
decisiones de una persona desde un JSON (lista de ``record_id``, ``aprobado``, ``uso`` y ``nota``) y exporta
lo aprobado, sin cifras, para el entrenamiento. No entrena: eso es de la GPU (072 T9b).

Uso:
    python tools/corpus_redaccion_pide.py --dataset <carpeta> [--pendientes 20]
    python tools/corpus_redaccion_pide.py --dataset <carpeta> --decisiones <json> --revisor "<nombre>"
    python tools/corpus_redaccion_pide.py --dataset <carpeta> --exportar <jsonl>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / 'src'
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))


def _fragmentos(dataset: Path) -> list[dict]:
    ruta = dataset / 'fragments.jsonl'
    with ruta.open(encoding='utf-8') as f:
        return [json.loads(x) for x in f if x.strip()]


def main(argv=None) -> int:
    # La salida se consume también desde subprocesos: la página de códigos de
    # Windows no debe convertir «redacción» en bytes incompatibles con UTF-8.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='Revisión humana del corpus PIDE para redactar y dar formato (072:RF-19).')
    p.add_argument('--dataset', type=Path, required=True, help='Carpeta del corpus con fragments.jsonl')
    p.add_argument('--registro', type=Path, help='Registro de revisión; por defecto revision_redaccion.jsonl del corpus')
    p.add_argument('--pendientes', type=int, default=0, help='Cuántos fragmentos pendientes enseñar')
    p.add_argument('--decisiones', type=Path, help='JSON con las decisiones de la persona que revisa')
    p.add_argument('--revisor', help='Nombre de la persona que revisa (obligatorio con --decisiones)')
    p.add_argument('--fecha', help='Fecha de la revisión, AAAA-MM-DD; por defecto hoy')
    p.add_argument('--exportar', type=Path, help='JSONL con los ejemplos aprobados, sin cifras')
    args = p.parse_args(argv)

    from convertersmartgrid.asistente.corpus_redaccion import (
        CorpusRedaccionError,
        ejemplos_para_entrenar,
        pendientes,
        registrar_revision,
        resumen,
    )

    if not (args.dataset / 'fragments.jsonl').is_file():
        print(f'ERROR: {args.dataset} no trae fragments.jsonl')
        return 2
    registro = args.registro or args.dataset / 'revision_redaccion.jsonl'
    fragmentos = _fragmentos(args.dataset)
    if args.decisiones:
        if not str(args.revisor or '').strip():
            print('ERROR: las decisiones piden --revisor: 072:RF-19 exige revisión humana con su nombre')
            return 2
        por_id = {str(f.get('record_id')): f for f in fragmentos}
        for d in json.loads(args.decisiones.read_text(encoding='utf-8')):
            f = por_id.get(str(d.get('record_id')))
            if f is None:
                print(f"ERROR: {d.get('record_id')} no está en el corpus")
                return 2
            try:
                registrar_revision(registro, f, revisor=args.revisor, origen='humano', aprobado=bool(d.get('aprobado')),
                                   uso=str(d.get('uso') or ''), fecha=args.fecha, nota=str(d.get('nota') or ''))
            except CorpusRedaccionError as exc:
                print(f"ERROR: {d.get('record_id')}: {exc}")
                return 2
    if args.exportar:
        ejemplos = ejemplos_para_entrenar(registro, fragmentos)
        args.exportar.parent.mkdir(parents=True, exist_ok=True)
        args.exportar.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in ejemplos), encoding='utf-8')
        print(f'Exportados: {len(ejemplos)} ejemplos a {args.exportar}')
    r = resumen(registro, fragmentos)
    print(f"Fragmentos de redacción: {r['fragmentos']}; revisados: {r['revisados']}; Aprobados: {r['aprobados']}; "
          f"rechazados: {r['rechazados']}; pendientes: {r['pendientes']}")
    for f in pendientes(registro, fragmentos)[:max(args.pendientes, 0)]:
        print(f"  pendiente {f['record_id']}: {f.get('relative_path')} · {str(f['text'])[:120]!r}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
