#!/usr/bin/env python
"""Revisión humana del corpus PIDE que enseña al asistente a redactar (spec 072, RF-19, RF-48 a RF-50).

Lee los fragmentos de un corpus de ``pide_dataset`` (``fragments.jsonl``) y su registro de revisión
(``revision_redaccion.jsonl``, en la misma carpeta salvo ``--registro``). Lista lo pendiente, anota las
decisiones desde un JSON (lista de ``record_id``, ``aprobado``, ``uso`` y ``nota``; o el ``decisiones.json`` de una
revisión, con su ``origen``, ``revisor``, ``fecha`` y ``huella_texto``), exporta lo aprobado sin cifras ni nombres
y lo sella en el formato que lee ``tools/asistente_qlora.py``. No entrena: eso es de la GPU (072 T9b).

Cada decisión guarda su origen (``--origen``, ``humano`` por defecto): ``humano`` o ``maestro`` (revisor
independiente). Las dos se exportan y se sellan, cada una marcada con el suyo; un fichero cuyas decisiones dicen otro
origen que ``--origen`` no se aplica, ni en parte, y cualquier otro origen no se registra (072:RF-48).
El catálogo de nombres (``--catalogo``) sale de los datos del espacio: JSON ``{"empresa": [...], "sede": [...],
"instalacion": [...]}``, una lista JSON o un texto con un nombre por línea.

Uso:
    python tools/corpus_redaccion_pide.py --dataset <carpeta> [--pendientes 20]
    python tools/corpus_redaccion_pide.py --dataset <carpeta> --decisiones <json> --revisor "<nombre>"
    python tools/corpus_redaccion_pide.py --dataset <carpeta> --decisiones <json> --origen maestro
    python tools/corpus_redaccion_pide.py --dataset <carpeta> --exportar <jsonl> [--catalogo <fichero>]
    python tools/corpus_redaccion_pide.py --dataset <carpeta> --sellar <carpeta nueva> [--catalogo <fichero>]
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


def _catalogo(ruta: Path | None):
    """El catálogo de nombres del espacio: JSON (objeto por clase o lista) o texto, un nombre por línea."""
    if ruta is None:
        return None
    texto = ruta.read_text(encoding='utf-8')
    if ruta.suffix.lower() == '.json':
        datos = json.loads(texto)
        if not isinstance(datos, (dict, list)):
            raise ValueError('el catálogo JSON es un objeto por clase o una lista de nombres')
        return datos
    return [x.strip() for x in texto.splitlines() if x.strip()]


def _decisiones(args, fragmentos, huella_texto, usos) -> tuple[list[tuple[dict, dict, str, str | None]], str | None]:
    """Comprueba el fichero entero antes de escribir: o entran todas sus decisiones o ninguna."""
    datos = json.loads(args.decisiones.read_text(encoding='utf-8'))
    if isinstance(datos, dict):
        datos = datos.get('decisiones')
    if not isinstance(datos, list):
        return [], 'el fichero de decisiones es una lista (o un objeto con «decisiones»)'
    por_id = {str(f.get('record_id')): f for f in fragmentos}
    listas = []
    for d in datos:
        rid = str(d.get('record_id'))
        f = por_id.get(rid)
        if f is None:
            return [], f'{rid} no está en el corpus'
        origen = str(d.get('origen') or args.origen)
        if origen != args.origen:
            return [], (f'{rid} es de origen «{origen}» y se aplica con --origen {args.origen}: cada decisión se '
                        'registra con el origen que tiene, y la del maestro nunca como humana')
        if args.origen == 'humano':
            revisor = str(args.revisor or '').strip()
            if not revisor:
                return [], 'las decisiones piden --revisor: la revisión es humana y lleva su nombre'
        else:
            revisor = str(d.get('revisor') or args.revisor or '').strip()
            if not revisor:
                return [], f'{rid} no dice quién la propone (--revisor o «revisor» en la decisión)'
        if d.get('huella_texto') and d['huella_texto'] != huella_texto(str(f.get('text') or '')):
            return [], f'{rid}: la huella del texto revisado no es la del texto actual; hay que revisarlo otra vez'
        if str(d.get('uso') or '') not in usos:
            return [], f"{rid}: uso «{d.get('uso')}» no autorizado"
        listas.append((d, f, revisor, args.fecha or d.get('fecha')))
    return listas, None


def main(argv=None) -> int:
    # La salida se consume también desde subprocesos: la página de códigos de
    # Windows no debe convertir «redacción» en bytes incompatibles con UTF-8.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='Revisión humana del corpus PIDE para redactar y dar formato (072:RF-19).')
    p.add_argument('--dataset', type=Path, required=True, help='Carpeta del corpus con fragments.jsonl')
    p.add_argument('--registro', type=Path, help='Registro de revisión; por defecto revision_redaccion.jsonl del corpus')
    p.add_argument('--pendientes', type=int, default=0, help='Cuántos fragmentos pendientes enseñar')
    p.add_argument('--decisiones', type=Path, help='JSON con las decisiones de la revisión')
    p.add_argument('--origen', choices=('humano', 'maestro'), default='humano',
                   help='Quién decidió (072:RF-48): una persona o el revisor independiente; queda en cada decisión')
    p.add_argument('--revisor', help='Nombre de la persona que revisa (obligatorio con --decisiones humanas)')
    p.add_argument('--fecha', help='Fecha de la revisión, AAAA-MM-DD; por defecto la de cada decisión o hoy')
    p.add_argument('--catalogo', type=Path, help='Nombres de empresa, sede e instalación que se ocultan (072:RF-49)')
    p.add_argument('--exportar', type=Path, help='JSONL con los ejemplos aprobados, sin cifras ni nombres')
    p.add_argument('--sellar', type=Path, help='Carpeta nueva con el corpus sellado para asistente_qlora (072:RF-50)')
    args = p.parse_args(argv)

    from convertersmartgrid.aplicacion.asistente.corpus_redaccion import (
        USOS,
        CorpusRedaccionError,
        ejemplos_para_entrenar,
        huella_texto,
        pendientes,
        registrar_revision,
        resumen,
        sellar_corpus_redaccion,
    )

    if not (args.dataset / 'fragments.jsonl').is_file():
        print(f'ERROR: {args.dataset} no trae fragments.jsonl')
        return 2
    registro = args.registro or args.dataset / 'revision_redaccion.jsonl'
    fragmentos = _fragmentos(args.dataset)
    try:
        catalogo = _catalogo(args.catalogo)
    except (OSError, ValueError) as exc:
        print(f'ERROR: catálogo ilegible: {exc}')
        return 2
    if args.decisiones:
        listas, error = _decisiones(args, fragmentos, huella_texto, USOS)
        if error:
            print(f'ERROR: {error}')
            return 2
        for d, f, revisor, fecha in listas:
            try:
                registrar_revision(registro, f, revisor=revisor, origen=args.origen, aprobado=bool(d.get('aprobado')),
                                   uso=str(d.get('uso') or ''), fecha=fecha, nota=str(d.get('nota') or ''))
            except CorpusRedaccionError as exc:
                print(f"ERROR: {d.get('record_id')}: {exc}")
                return 2
        print(f'Registradas: {len(listas)} decisiones de origen {args.origen}')
    ejemplos = ejemplos_para_entrenar(registro, fragmentos, catalogo=catalogo)
    if args.exportar:
        args.exportar.parent.mkdir(parents=True, exist_ok=True)
        args.exportar.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in ejemplos), encoding='utf-8')
        print(f'Exportados: {len(ejemplos)} ejemplos a {args.exportar}')
    if args.sellar:
        try:
            meta = sellar_corpus_redaccion(args.dataset, args.sellar, registro=registro, catalogo=catalogo)
        except ValueError as exc:
            print(f'ERROR: {exc}')
            return 2
        print(f"Sellado: {sum(meta['por_particion'].values())} ejemplos en {args.sellar} "
              f"({json.dumps(meta['por_particion'], ensure_ascii=False)})")
    r = resumen(registro, fragmentos)
    print(f"Fragmentos de redacción: {r['fragmentos']}; revisados: {r['revisados']}; Aprobados: {r['aprobados']}; "
          f"rechazados: {r['rechazados']}; pendientes: {r['pendientes']}")
    por_origen = {o: sum(e['origen'] == o for e in ejemplos) for o in ('humano', 'maestro')}
    print(f"Exportables: {len(ejemplos)} (humano: {por_origen['humano']}, maestro: {por_origen['maestro']})")
    for f in pendientes(registro, fragmentos)[:max(args.pendientes, 0)]:
        print(f"  pendiente {f['record_id']}: {f.get('relative_path')} · {str(f['text'])[:120]!r}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
