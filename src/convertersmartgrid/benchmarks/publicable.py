"""Benchmark publicable: una red sintética con las estadísticas agregadas del origen, sin un solo tramo real (112:RF-13, RF-14).

Lo que deriva de una red real se reidentifica por su huella de longitudes aunque se perturbe (aclaración de RF-13 y
RF-14): es de uso local. Lo publicable se genera con ``ExportSpec`` a partir de los agregados del origen —número de
alimentadores y de tramos, y los cuantiles de longitud y de carga— y el control del atacante no debe identificar
ningún alimentador del origen en él.

Condición del auditor: un agregado solo se usa si junta al menos 5 alimentadores y 500 tramos, porque los agregados
de una red pequeña también la delatan. Con menos se agrupan las redes de la misma entrega; si aun así no llega, no se
emite y se dice por qué. Los mínimos van en el manifiesto y se pueden subir, nunca bajar.
"""
from __future__ import annotations

import math
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .geometria import largos_por_alimentador

MINIMOS = {'alimentadores': 5, 'tramos': 500}
#: Cuantiles que se publican: p0, p10 … p100. Se redondean (longitud al metro, carga al kW) para no copiar un extremo.
CUANTILES = tuple(i / 10 for i in range(11))


class AgregadoInsuficiente(ValueError):
    """El origen no junta los mínimos ni agrupado con su entrega: sus agregados lo delatarían."""


def minimos_para(pedidos: Mapping[str, int] | None) -> dict[str, int]:
    """Los mínimos de la spec, subidos si se pide; un mínimo por debajo del de la spec se rechaza."""
    salida = dict(MINIMOS)
    for clave, valor in (pedidos or {}).items():
        if clave not in MINIMOS:
            raise ValueError(f'mínimo desconocido: {clave}')
        if int(valor) < MINIMOS[clave]:
            raise ValueError(f'el mínimo de {clave} no se puede bajar de {MINIMOS[clave]}: se pidió {valor}')
        salida[clave] = int(valor)
    return salida


def _cargas(ficheros) -> list[float]:
    carga = next(f for f in ficheros if f.nombre == 'CARGA.txt')
    salida = []
    for e in carga.entradas:
        if e[0] == 'fila' and e[1] == 'CUSTOMER LOADS':
            try:
                salida.append(float(e[2].get('Value1') or 'nan'))
            except ValueError:
                continue
    return [x for x in salida if np.isfinite(x)]


def estadisticas(trios_leidos: Sequence[list]) -> dict[str, Any]:
    """Los agregados de una o varias redes de la misma entrega: recuentos y cuantiles, nunca un tramo."""
    por_alim: dict[str, list[float]] = {}
    cargas: list[float] = []
    for k, ficheros in enumerate(trios_leidos):
        for red, largos in largos_por_alimentador(ficheros).items():
            por_alim[f'{k}:{red}'] = largos
        cargas += _cargas(ficheros)
    todos = [x for v in por_alim.values() for x in v]
    q = lambda xs, redondeo: [round(float(v), redondeo) for v in np.quantile(xs, CUANTILES)] if xs else []  # noqa: E731
    return {'redes_agrupadas': len(trios_leidos), 'alimentadores': len(por_alim), 'tramos': len(todos),
            'cargas': len(cargas), 'longitudes_m': q(todos, 0), 'cargas_kw': q(cargas, 0)}


def generar_publicable(trios: Sequence[tuple], destino: Path | str, *, semilla: int | None = None,
                       minimos: Mapping[str, int] | None = None, raiz: Path | None = None) -> dict[str, Any]:
    """Genera en ``destino`` la red sintética publicable de las redes de una entrega. Devuelve su manifiesto."""
    from . import manifiesto as M
    from . import redes as R
    from .geometria import AMPLITUD_POR_DEFECTO, identificados
    from .semilla import guardar_secreta, nueva_semilla, semilla_publica, validar_secreta
    from .sintetico import ExportSpec, write_export

    destino = Path(destino)
    if destino.exists():
        raise FileExistsError(f'{destino.name} ya existe: un benchmark emitido no se sobrescribe')
    limites = minimos_para(minimos)
    semilla = validar_secreta(semilla) if semilla is not None else nueva_semilla()
    leidos = [[R.leer_fichero(r, n) for r, n in zip(trio, R.NOMBRES)] for trio in trios]
    # Las redes de la entrega se agregan juntas (condición del auditor): una red pequeña sola no llegaría a los mínimos,
    # y con las demás sus agregados ya no la delatan. Si la entrega entera no llega, no se emite.
    est = estadisticas(leidos)
    if est['alimentadores'] < limites['alimentadores'] or est['tramos'] < limites['tramos']:
        raise AgregadoInsuficiente(
            f'no se emite: la entrega junta {est["alimentadores"]} alimentadores y {est["tramos"]} tramos, y el '
            f'publicable necesita al menos {limites["alimentadores"]} alimentadores y {limites["tramos"]} tramos '
            '(con menos, sus agregados delatarían la red)')
    publica = semilla_publica(semilla)
    # Sin semilla de tamaños: con ella, ExportSpec sortea el tamaño de cada alimentador alrededor del típico y el total
    # de tramos se aleja del agregado (757 pedidos dieron 279). Con el tamaño redondeado hacia arriba, el publicable
    # tiene al menos tantos tramos como el origen, y por tanto nunca menos que el mínimo.
    spec = ExportSpec(feeders=est['alimentadores'],
                      sections_per_feeder=max(1, math.ceil(est['tramos'] / est['alimentadores'])),
                      loads_per_feeder=max(1, math.ceil(est['cargas'] / est['alimentadores'])),
                      seed=None, layout='reducido', naming='plain',
                      longitudes_m=tuple(est['longitudes_m']), cargas_kw=tuple(max(v, 0.0) for v in est['cargas_kw']))
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.parent / f'.csg-stage-benchmark-{destino.name}'
    if temporal.exists():
        shutil.rmtree(temporal)
    try:
        write_export(spec, temporal)
        sinteticos = largos_por_alimentador([R.leer_fichero(temporal / n, n) for n in R.NOMBRES])
        originales = {}
        for k, ficheros in enumerate(leidos):
            for red, largos in largos_por_alimentador(ficheros).items():
                originales[f'{k}:{red}'] = largos
        pillados = identificados(originales, sinteticos, AMPLITUD_POR_DEFECTO)
        if pillados:
            raise AgregadoInsuficiente(f'no se emite: el control identifica {len(pillados)} alimentador(es) del '
                                       'origen en la red sintética')
        huellas = [M.huella_ficheros(t) for t in trios]
        manifiesto = M.construir_publicable(huellas_origen=huellas, semilla_publica=publica, minimos=limites,
                                            estadisticas=est, carpeta=temporal,
                                            geometria={'trazado': 'sintetico', 'margen': AMPLITUD_POR_DEFECTO,
                                                       'identificados': 0, 'alimentadores': len(sinteticos)})
        M.escribir(temporal, manifiesto)
        for h in huellas:
            guardar_secreta(h, semilla, raiz=raiz)
        os.replace(temporal, destino)
    except BaseException:
        shutil.rmtree(temporal, ignore_errors=True)
        raise
    return manifiesto
