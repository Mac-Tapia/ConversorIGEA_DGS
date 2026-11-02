#!/usr/bin/env python
"""Aceptación nativa de la restitución del servidor de DIgSILENT (spec 064, T7).

Recorre la cadena de la web sin el HTTP: ``services._guion_pf`` → ``jobs.run_process`` →
``pf_cliente`` → ``pf_servidor.atender``, con cuatro órdenes de ``restitucion_pf.py`` sobre
una copia exclusiva de un proyecto importado:

1. ``copiar`` el origen como ``PRUEBA064_<hora>`` (el original no se toca);
2. ``alterar_y_fallar``: cambia caso, hora, escenario y variación y termina con código 1;
3. ``leer``: otra orden que confirma que el servidor dejó el estado como estaba en 2;
4. ``borrar`` la copia, también si algo falló antes.

Escribe la evidencia (fotos, códigos y el registro de cada orden) en ``--out``. Sale con 0
solo si la orden fallida dice qué restituyó (064:RF-6) y la lectura coincide con la foto
anterior a la orden (064:RF-5).

    python tools/aceptar_restitucion_pf.py --origen 20261101-101524_CSG_0205 --out evidencia.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))


def _contexto(registro: list[str]):
    from convertersmartgrid.web.jobs import Job, JobContext

    def emit(_wid: str, kind: str, data: dict) -> None:
        if kind == 'log' and data.get('text'):
            registro.append(str(data['text']))
            print(data['text'], flush=True)

    job = Job(kind='aceptacion_064', title='Aceptación de la restitución', workspace_id='acept064',
              lane='powerfactory', fn=lambda _ctx: None)
    return JobContext(job, emit)


def aceptar(origen: str, carpeta: str, trabajo: Path) -> dict:
    from convertersmartgrid.web import services
    from convertersmartgrid.web.workspace import Workspace

    ws = Workspace(id='acept064', root=trabajo / 'espacio')
    pasos: dict = {}

    def orden(accion: str, copia: str | None = None) -> tuple[int, dict, list[str]]:
        registro: list[str] = []
        rc, informe, _ruta = services._guion_pf(
            ws, _contexto(registro), 'restitucion_pf.py',
            {'accion': accion, 'origen': origen, 'copia': copia, 'folder': carpeta},
            nombre=f'restitucion_{accion}', cancelable=False, limite_s=900)
        pasos[accion] = {'codigo': rc, 'informe': informe, 'registro': registro}
        return rc, informe, registro

    rc, copiado, _ = orden('copiar')
    copia = copiado.get('copia')
    if rc != 0 or not copia:
        return {'aceptada': False, 'motivo': 'no se pudo hacer la copia', 'pasos': pasos}
    try:
        rc_f, alterado, registro_f = orden('alterar_y_fallar', copia)
        _rc, leido, _ = orden('leer', copia)
    finally:
        orden('borrar', copia)
    antes = alterado.get('antes')
    cambio = alterado.get('alterado') != antes
    dice = any('064:RF-5' in linea and 'como estaba al empezar' in linea for linea in registro_f)
    igual = leido.get('foto') == antes
    borrada = bool((pasos.get('borrar') or {}).get('informe', {}).get('borrada'))
    return {'aceptada': rc_f == 1 and cambio and dice and igual and borrada,
            'origen': origen, 'copia': copia, 'foto_antes': antes,
            'foto_alterada': alterado.get('alterado'), 'foto_leida_despues': leido.get('foto'),
            'la_orden_cambio_el_estado': cambio, 'la_orden_fallo': rc_f == 1,
            'el_registro_dice_lo_restituido': dice, 'la_lectura_coincide': igual,
            'copia_borrada': borrada, 'pasos': pasos}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Aceptación nativa de la restitución (spec 064, T7)')
    p.add_argument('--origen', required=True, help='Proyecto importado que se copia (no se toca)')
    p.add_argument('--carpeta', default=None, help='Carpeta de DIgSILENT; por defecto, la del perfil')
    p.add_argument('--out', required=True, type=Path, help='JSON de evidencia')
    args = p.parse_args(argv)
    from convertersmartgrid.carpeta_pf import nombre_de_perfil

    with tempfile.TemporaryDirectory(prefix='csg-acept064-') as tmp:
        evidencia = aceptar(args.origen, args.carpeta or nombre_de_perfil(), Path(tmp))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidencia, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Aceptada: {evidencia['aceptada']}  ·  evidencia en {args.out}", flush=True)
    return 0 if evidencia['aceptada'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
