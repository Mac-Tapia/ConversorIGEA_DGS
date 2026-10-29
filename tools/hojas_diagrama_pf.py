#!/usr/bin/env python
"""Hoja de cada diagrama frente a sus gráficos, en DIgSILENT (spec 022, RF-93).

DIgSILENT dimensiona la hoja de un diagrama importado con el recuadro de sus gráficos y la
orienta él (``cDrawOrient``: 1 apaisada, 0 vertical). No había ninguna herramienta que lo
comprobara en DIgSILENT (``prueba_representacion.py`` mira el DGS): esta dice, por cada
``IntGrfnet``, el recuadro de sus gráficos y conectores, su formato, su orientación y si todo
cae dentro. Solo lee.

En Nasca por SET (2026-10-29) la SET 52, la 53 y la 56 son más altas que anchas y DIgSILENT
les dio hoja vertical; los vectores de los conectores llevan −1 en los puntos sin usar, que
no son del dibujo.

    python tools/hojas_diagrama_pf.py --proyecto 20261029-081235_IGEA_SISTEMA_NASCA \
        --carpeta <carpeta del perfil de empresa> [--output-json hojas.json]

Códigos de salida: 0 todas dentro, 1 alguna fuera o error inesperado, 2 proyecto que no
existe, 3 API de PowerFactory no disponible.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / 'src'), str(RAIZ / 'tools')]

#: ``cDrawOrient`` de DIgSILENT: 1 apaisada (horizontal), 0 vertical.
HORIZONTAL, VERTICAL = 1, 0
#: Lo que DIgSILENT pone en los puntos sin usar del vector de un conector.
SIN_PUNTO = -1.0


def _valor(obj, nombre: str):
    try:
        return obj.GetAttribute(nombre)
    except Exception:  # noqa: BLE001 - atributo ausente en otra versión o sin asignar
        return getattr(obj, nombre, None)


def _num(obj, nombre: str) -> float | None:
    valor = _valor(obj, nombre)
    return None if valor is None else float(valor)


def puntos_del_conector(rx, ry) -> list[tuple[float, float]]:
    """Los puntos del conector hasta el primero sin usar (−1, −1)."""
    out = []
    for x, y in zip(rx or [], ry or []):
        if float(x) == SIN_PUNTO and float(y) == SIN_PUNTO:
            break
        out.append((float(x), float(y)))
    return out


def recuadro(diagrama) -> tuple[float, float, float, float] | None:
    """``(xmin, ymin, xmax, ymax)`` de los gráficos y conectores del diagrama, o ``None``."""
    xs: list[float] = []
    ys: list[float] = []
    for g in diagrama.GetContents('*.IntGrf', 0) or []:
        x, y = _num(g, 'rCenterX'), _num(g, 'rCenterY')
        if x is not None and y is not None:
            xs.append(x)
            ys.append(y)
        for c in g.GetContents('*.IntGrfcon', 0) or []:
            for px, py in puntos_del_conector(_valor(c, 'rX'), _valor(c, 'rY')):
                xs.append(px)
                ys.append(py)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def tamano_del_formato(nombre: str, formatos: dict[str, tuple[float, float]]) -> tuple[float, float] | None:
    """Ancho y alto del formato: el de la biblioteca o el «(ancho×alto)» que DIgSILENT pone en
    el nombre de la hoja que crea a la medida."""
    if nombre in formatos:
        return formatos[nombre]
    m = re.search(r'\((\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)\)', nombre or '')
    return (float(m.group(1)), float(m.group(2))) if m else None


def hoja_efectiva(tam: tuple[float, float] | None, orientacion: int) -> tuple[float, float] | None:
    """La hoja con su orientación: vertical pone el lado mayor en el alto."""
    if tam is None:
        return None
    mayor, menor = max(tam), min(tam)
    return (menor, mayor) if orientacion == VERTICAL else (mayor, menor)


def orientacion_de(diagrama) -> int:
    """``cDrawOrient`` del diagrama; sin él, horizontal. El 0 es vertical, no «sin valor»."""
    valor = _num(diagrama, 'cDrawOrient')
    return HORIZONTAL if valor is None else int(valor)


def revisar(diagrama, formatos: dict[str, tuple[float, float]]) -> dict:
    """RF-93: la hoja del diagrama frente al recuadro de sus gráficos."""
    caja = recuadro(diagrama)
    formato = str(_valor(diagrama, 'cDrawFormat') or '')
    orientacion = orientacion_de(diagrama)
    hoja = hoja_efectiva(tamano_del_formato(formato, formatos), orientacion)
    dentro = (caja is not None and hoja is not None and caja[0] >= 0 and caja[1] >= 0
              and caja[2] <= hoja[0] and caja[3] <= hoja[1])
    return {'diagrama': diagrama.loc_name, 'formato': formato,
            'orientacion': 'vertical' if orientacion == VERTICAL else 'horizontal',
            'hoja': list(hoja) if hoja else None, 'recuadro': list(caja) if caja else None,
            'dentro': dentro}


def _formatos(app) -> dict[str, tuple[float, float]]:
    out = {}
    for lib in (app.GetGlobalLibrary(), app.GetProjectFolder('lib')):
        for f in (lib.GetContents('*.SetFormat', 1) if lib is not None else []) or []:
            x, y = _num(f, 'iSizeX'), _num(f, 'iSizeY')
            if x and y:
                out[f.loc_name] = (x, y)
    return out


def ejecutar(app, plan: dict) -> tuple[dict, int]:
    """Revisa los diagramas del proyecto del plan. Devuelve (informe, código)."""
    from cargas_pf import activar_proyecto

    informe: dict = {'project': plan.get('project'), 'diagramas': []}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r}"}, 2
    formatos = _formatos(app)
    informe['diagramas'] = [revisar(d, formatos)
                            for d in sorted(proyecto.GetContents('*.IntGrfnet', 1) or [],
                                            key=lambda d: d.loc_name)]
    informe['todas_dentro'] = all(d['dentro'] for d in informe['diagramas'])
    return informe, 0 if informe['todas_dentro'] else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Hoja de cada diagrama de un proyecto de DIgSILENT '
                                            'frente a sus gráficos, de solo lectura (spec 022, RF-93)')
    p.add_argument('--proyecto', required=True, help='Nombre del proyecto en DIgSILENT')
    p.add_argument('--carpeta', help='Carpeta de proyectos del usuario (perfil de empresa)')
    p.add_argument('--output-json', help='Informe en JSON')
    args = p.parse_args(argv)
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('hojas_diagrama_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        informe, codigo = ejecutar(app, {'project': args.proyecto, 'folder': args.carpeta})
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito
        informe, codigo = {'project': args.proyecto, 'error': repr(exc),
                           'traza': traceback.format_exc()}, 1
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n',
                                          encoding='utf-8')
    for d in informe.get('diagramas', []):
        caja = d['recuadro'] or [0, 0, 0, 0]
        print(f"  {d['diagrama']}: gráficos x {caja[0]:.0f}..{caja[2]:.0f}, y {caja[1]:.0f}..{caja[3]:.0f}; "
              f"hoja «{d['formato']}» {d['orientacion']} {d['hoja']}; "
              f"{'todo dentro' if d['dentro'] else 'FUERA'}", flush=True)
    if informe.get('error'):
        print(f"ERROR: {informe['error']}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
