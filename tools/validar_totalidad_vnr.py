#!/usr/bin/env python3
"""Cruza lo que lista la web con la copia VNR-GIS restaurada, salida por salida (Spec 080).

    python tools/validar_totalidad_vnr.py --espacio <id> --web http://127.0.0.1:8765

El usuario, 2026-11-02: «validar de cada empresa que lo cargado sea la totalidad de alimentadores,
sin excepción alguna». Lo que dice el propio conversor no vale como prueba: Electro Sur Este
listaba 1 993 alimentadores sin aviso y perdía 47 salidas con su SED. Por eso aquí se cuenta con
consultas propias a la base, sin usar el lector. Termina con error si algo no cuadra.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


def contar_en_base(cursor) -> dict:
    """{salidas: {código: (tramos, SED)}, tramos, seds}, sin pasar por el lector."""
    cursor.execute(
        'SELECT RTRIM(s.CodSalidaMT), RTRIM(s.EtiquetaSalida), '
        '(SELECT COUNT(*) FROM mtTramo t WHERE t.CodSalidaMT = s.CodSalidaMT), '
        '(SELECT COUNT(*) FROM Sed e WHERE e.CodSalidaMT = s.CodSalidaMT) FROM mtSalida s')
    salidas, etiquetas = {}, {}
    for codigo, etiqueta, tramos_salida, seds_salida in cursor.fetchall():
        codigo = str(codigo).strip()
        salidas[codigo] = (int(tramos_salida), int(seds_salida))
        etiquetas[codigo] = str(etiqueta or '').strip()
    cursor.execute('SELECT COUNT(*) FROM mtTramo')
    tramos = int(cursor.fetchone()[0])
    cursor.execute('SELECT COUNT(*) FROM Sed')
    seds = int(cursor.fetchone()[0])
    return {'salidas': salidas, 'etiquetas': etiquetas, 'tramos': tramos, 'seds': seds}


def cruzar(base: dict, web: list[dict]) -> dict:
    """080:RF-29 a RF-31: qué falta, qué sobra y qué no tiene red que cargar."""
    en_web = {str(f.get('network_id') or f.get('feeder')).strip(): f for f in web}
    salidas = base['salidas']
    # La web lista el código operativo (056:RF-7): «A01» de Luz del Sur es la salida 100683102.
    # Una salida se da por cargada por su código o por su etiqueta, sin tomar una por otra.
    etiquetas = base.get('etiquetas') or {}
    nombres = {c: {c, etiquetas.get(c, '')} - {''} for c in salidas}
    conocidos = {n for grupo in nombres.values() for n in grupo}
    con_red = {c for c, (t, e) in salidas.items() if t or e}
    cargadas = {c for c in salidas if nombres[c] & set(en_web)}
    faltan = [{'salida': c, 'tramos': salidas[c][0], 'sed': salidas[c][1]}
              for c in sorted(con_red - cargadas)]
    sobran = sorted(set(en_web) - conocidos)
    seds_web = sum(int(f.get('loads') or 0) for f in web)
    tramos_web = sum(int(f.get('sections') or 0) for f in web)
    return {
        'ok': not faltan and not sobran and seds_web == base['seds'],
        'salidas': {'base': len(salidas), 'con_red': len(con_red), 'web': len(en_web)},
        'sed': {'base': base['seds'], 'web': seds_web},
        # Un tramo de extremos coincidentes o unido a su padre no es un tramo eléctrico: se informa
        # la diferencia, sin que sea un fallo, para que se vea.
        'tramos': {'base': base['tramos'], 'web': tramos_web,
                   'no_electricos': base['tramos'] - tramos_web},
        'faltan': faltan,
        'sobran': sobran,
        'sin_red': sorted(set(salidas) - con_red),
    }


def _leer(url: str):
    with urllib.request.urlopen(url, timeout=120) as respuesta:
        return json.load(respuesta)


def alimentadores_de(respuesta) -> list[dict]:
    """La respuesta de ``/feeders``: ``{"feeders": […]}``."""
    return respuesta['feeders'] if isinstance(respuesta, dict) else respuesta


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--espacio', required=True, help='Espacio de trabajo de la web')
    p.add_argument('--web', default='http://127.0.0.1:8765', help='Dirección de la web')
    p.add_argument('--salida', type=Path, help='Guardar el informe en este JSON')
    args = p.parse_args(argv)

    from vnr_etl.connectors import sqlserver_vnr as sv

    espacio = _leer(f'{args.web}/api/workspaces/{args.espacio}')
    entrada = (espacio.get('inputs') or {}).get('vnr_package') or {}
    if not entrada.get('path'):
        print('Ese espacio no tiene una copia VNR-GIS asignada.', file=sys.stderr)
        return 2
    if not espacio.get('loaded'):
        # Tras reiniciar la web un espacio queda sin cargar: 0 frente a 2 113 no es una carga
        # incompleta, y decir «no cuadra» confundía (Electro Sur Este, 2026-11-03).
        print('Ese espacio no está cargado: pulse «Cargar / listar alimentadores» antes de validar.',
              file=sys.stderr)
        return 2
    base = f"CSG_VNR_{sv.huella(entrada['path'])[:16]}"
    conexion = sv.conectar(sv.SERVIDOR, base)
    informe = cruzar(contar_en_base(conexion.cursor()),
                     alimentadores_de(_leer(f'{args.web}/api/workspaces/{args.espacio}/feeders')))
    informe.update(copia=entrada.get('name'), base=base)
    texto = json.dumps(informe, ensure_ascii=False, indent=1)
    if args.salida:
        args.salida.write_text(texto, encoding='utf-8')
    resumen = {k: v for k, v in informe.items() if k != 'sin_red'}
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(f"Salidas sin tramos ni SED ({len(informe['sin_red'])}): {', '.join(informe['sin_red'])}")
    print('TOTALIDAD: OK' if informe['ok'] else 'TOTALIDAD: NO CUADRA')
    return 0 if informe['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
