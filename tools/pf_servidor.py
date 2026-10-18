#!/usr/bin/env python
"""Proceso que mantiene DIgSILENT abierto y atiende órdenes de guiones (spec 019, RF-7 a RF-9).

Cada guion de DIgSILENT conectaba y activaba el proyecto desde cero: en CA101
(2026-10-15) unos 5 minutos por ejecución, también para una lectura de un segundo. Este
proceso toma el turno del motor (``pf_arnes``), conecta una vez y atiende las órdenes que
deja ``tools/pf_cliente.py`` en la cola: ejecuta el ``main`` del guion pedido dentro de
su proceso, con su salida a un fichero que el cliente va leyendo, y el proyecto que
quedó activo sigue activo para la orden siguiente. Sin órdenes durante 2 minutos se
cierra y suelta el turno (usuario, 2026-10-15).

    python tools/pf_servidor.py [--inactividad 120]

Códigos de salida: 0 cerrado por inactividad, 3 sin DIgSILENT.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / 'src'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from igea_dgs import pf_arnes  # noqa: E402


def _cargar(guion: str):
    """El módulo del guion, cargado de nuevo en cada orden: sin estado de la anterior."""
    if guion not in pf_arnes.GUIONES_SERVIBLES:
        raise ValueError(f'el servidor no atiende {guion!r}')
    spec = importlib.util.spec_from_file_location(f'_orden_{guion[:-3]}', HERE / guion)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def atender(orden: dict, cola: Path) -> int:
    """Ejecuta una orden; su salida va a ``<id>.log`` y su código a ``<id>.fin.json``."""
    log = cola / f"{orden['id']}.log"
    with open(log, 'w', encoding='utf-8', buffering=1) as f, redirect_stdout(f), \
            redirect_stderr(f):
        try:
            codigo = _cargar(orden['guion']).main(list(orden.get('argv') or []))
        except SystemExit as exc:
            codigo = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        except Exception:  # noqa: BLE001 - la orden falla, el servidor sigue
            traceback.print_exc()
            codigo = 1
    (cola / f"{orden['id']}.fin.json").write_text(json.dumps({'codigo': codigo or 0}),
                                                  encoding='utf-8')
    return codigo or 0


def servir(inactividad_s: float = pf_arnes.INACTIVIDAD_S, *,
           reloj=time.monotonic, dormir=time.sleep) -> int:
    """Atiende la cola hasta ``inactividad_s`` sin órdenes (RF-7, RF-8)."""
    cola = pf_arnes.ruta_cola()
    cola.mkdir(parents=True, exist_ok=True)
    ultima = reloj()
    (cola / pf_arnes.CIERRE).unlink(missing_ok=True)       # un pedido viejo no cierra este
    while reloj() - ultima < inactividad_s:
        ordenes = sorted(cola.glob('*.orden.json'))
        if not ordenes:
            if (cola / pf_arnes.CIERRE).exists():
                # 019:RF-14: un guion suelto espera el motor y no hay nada que atender.
                (cola / pf_arnes.CIERRE).unlink(missing_ok=True)
                print('Otro guion pide el motor y no hay órdenes: se cierra (019:RF-14).',
                      flush=True)
                return 0
            dormir(0.3)
            continue
        fichero = ordenes[0]
        en_curso = fichero.with_name(fichero.name.replace('.orden.json', '.en_curso.json'))
        try:
            fichero.replace(en_curso)
        except OSError:
            continue
        orden = json.loads(en_curso.read_text(encoding='utf-8'))
        print(f"Orden {orden['id']}: {orden['guion']}", flush=True)
        atender(orden, cola)
        en_curso.unlink(missing_ok=True)
        ultima = reloj()
    print(f'Sin órdenes en {inactividad_s:g} s: se cierra (019:RF-8).', flush=True)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Proceso que mantiene DIgSILENT abierto (spec 019)')
    p.add_argument('--inactividad', type=float, default=pf_arnes.INACTIVIDAD_S,
                   help='Segundos sin órdenes antes de cerrarse')
    args = p.parse_args(argv)
    try:
        app = pf_arnes.conectar(pf_arnes.SERVIDOR)
    except pf_arnes.PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    pf_arnes.compartir_app(app)
    try:
        return servir(args.inactividad)
    finally:
        pf_arnes.compartir_app(None)
        pf_arnes.soltar_turno()


if __name__ == '__main__':
    raise SystemExit(main())
