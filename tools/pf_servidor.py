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
import os
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


def _sin_cliente(orden: dict, vivo) -> bool:
    """Si la orden es de un cliente que ya no la espera (019:RF-17).

    2026-10-19: la web cortó «Leer proyectos» a los 180 s y su orden se quedó en la cola; el
    servidor siguiente la ejecutó primero, casi 3 min para nadie, y la lectura que el
    operador relanzó agotó sus 180 s esperando detrás. Una orden sin cliente anotado (de
    una versión anterior) se atiende.
    """
    cliente = orden.get('cliente')
    if not cliente:
        return False
    return not pf_arnes.dueno_vivo({'pid': cliente, 'inicio': orden.get('cliente_inicio')},
                                   vivo)


def _decir(texto: str) -> None:
    """Línea de ``servidor.log`` con su hora (019:RF-21).

    2026-10-19: el registro sin horas no decía si el servidor tardó en conectar o en
    empezar la orden, y hubo que deducirlo de las fechas de los ficheros de la cola.
    """
    print(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {texto}', flush=True)


#: Restos de la cola (``.log``, ``.fin.json``, ``.tmp``) más viejos que esto se borran.
RESTOS_S = 24 * 3600.0


def limpiar_cola(cola: Path, ahora=time.time) -> None:
    """Deja la cola como la necesita un servidor recién arrancado (019:RF-21).

    Con el turno en la mano no hay otro servidor: una orden ``en_curso`` es de uno que
    murió a mitad, y su cliente, si sigue esperando, recibe el fin con código 3 en vez de
    esperar para siempre. Los restos de clientes cortados (días de ``.log`` y ``.fin``)
    se borran.
    """
    for en_curso in cola.glob('*.en_curso.json'):
        ident = en_curso.name[:-len('.en_curso.json')]
        with open(cola / f'{ident}.log', 'a', encoding='utf-8') as f:
            f.write('ERROR: el proceso de DIgSILENT que atendía la orden murió a mitad '
                    '(019:RF-8).\n')
        (cola / f'{ident}.fin.json').write_text(json.dumps({'codigo': 3}), encoding='utf-8')
        en_curso.unlink(missing_ok=True)
        _decir(f'Orden {ident} de un proceso anterior cerrada con código 3.')
    for patron in ('*.log', '*.fin.json', '*.tmp'):
        for resto in cola.glob(patron):
            try:
                if resto.name != 'servidor.log' and ahora() - resto.stat().st_mtime > RESTOS_S:
                    resto.unlink()
            except OSError:
                pass


def servir(inactividad_s: float = pf_arnes.INACTIVIDAD_S, *,
           reloj=time.monotonic, dormir=time.sleep, vivo=pf_arnes.pid_vivo) -> int:
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
                _decir('Otro guion pide el motor y no hay órdenes: se cierra (019:RF-14).')
                return 0
            dormir(0.3)
            continue
        fichero = ordenes[0]
        en_curso = fichero.with_name(fichero.name.replace('.orden.json', '.en_curso.json'))
        try:
            fichero.replace(en_curso)
        except OSError:
            continue
        try:
            orden = json.loads(en_curso.read_text(encoding='utf-8'))
            orden['id'], orden['guion']
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Una orden ilegible no tumba el servidor ni bloquea las de detrás.
            _decir(f'Orden {fichero.name} ilegible, se descarta: {exc}')
            en_curso.unlink(missing_ok=True)
            continue
        if _sin_cliente(orden, vivo):
            _decir(f"Orden {orden['id']} descartada: su cliente (proceso {orden['cliente']}) "
                   'ya no la espera (019:RF-17).')
            en_curso.unlink(missing_ok=True)
            continue
        _decir(f"Orden {orden['id']}: {orden['guion']}")
        inicio = reloj()
        codigo = atender(orden, cola)
        en_curso.unlink(missing_ok=True)
        _decir(f"Orden {orden['id']} terminada con código {codigo} en {reloj() - inicio:.0f} s.")
        ultima = reloj()
    _decir(f'Sin órdenes en {inactividad_s:g} s: se cierra (019:RF-8).')
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Proceso que mantiene DIgSILENT abierto (spec 019)')
    p.add_argument('--inactividad', type=float, default=pf_arnes.INACTIVIDAD_S,
                   help='Segundos sin órdenes antes de cerrarse')
    args = p.parse_args(argv)
    _decir(f'Proceso {os.getpid()}: conectando con DIgSILENT.')
    try:
        app = pf_arnes.conectar(pf_arnes.SERVIDOR)
    except pf_arnes.PFNoDisponible as exc:
        _decir(f'ERROR: {exc}')
        return 3
    pf_arnes.compartir_app(app)
    try:
        limpiar_cola(pf_arnes.ruta_cola())
        return servir(args.inactividad)
    finally:
        pf_arnes.compartir_app(None)
        # 019:RF-19: DIgSILENT se cierra al salir el proceso; hasta que muera el turno
        # sigue siendo suyo, y ``servidor_vivo`` ya no lo da por servidor.
        pf_arnes.soltar_turno(al_salir=True)


if __name__ == '__main__':
    raise SystemExit(main())
