"""Prueba sellada antes de elegir modelo e informe con todos los resultados (112:RF-7, RF-8, RF-9).

La prueba de cada cohorte se sella antes de entrenar o elegir ningún modelo, como ``HUELLA`` en
``asistente/prueba_sellada*.py``: se escribe con apertura exclusiva (no se sobrescribe) y su huella va al manifiesto;
abrirla la recalcula y la rechaza si cambió. El informe publica todos los candidatos de todas las cohortes, también
los que pierden contra la base o no pasan la puerta, con su motivo: un informe que solo enseña lo que gana exagera.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...dominio.evaluacion_harness.contratos import canonico, huella
from ..evaluacion_harness.publicacion import leer_json, publicar
from ...dominio.util import cuenta

NOMBRE_PRUEBA = 'prueba_sellada.json'
ESQUEMA_PRUEBA = 'csg-prueba-sellada-v1'


class PruebaAlterada(ValueError):
    """La prueba sellada no tiene la huella con que se selló."""


def _contenido(cohortes) -> dict[str, Any]:
    return {'esquema': ESQUEMA_PRUEBA,
            'cohortes': [{'nombre': c.nombre, 'tipo': c.tipo, 'retenida': c.retenida,
                          'politica_hash': c.particiones.politica_hash, 'prueba': list(c.particiones.prueba)}
                         for c in sorted(cohortes, key=lambda c: c.nombre)]}


def sellar_prueba(cohortes, carpeta: Path | str) -> str:
    """Escribe la prueba de cada cohorte con apertura exclusiva y devuelve su huella (para el manifiesto)."""
    contenido = _contenido(cohortes)
    ruta = Path(carpeta) / NOMBRE_PRUEBA
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open('xb') as f:          # FileExistsError si ya estaba sellada: no se sobrescribe
        f.write(canonico(contenido))
    return huella(contenido)


def abrir_prueba(carpeta: Path | str, huella_sellada: str) -> dict[str, Any]:
    dato = leer_json(Path(carpeta) / NOMBRE_PRUEBA)
    if huella(dato) != huella_sellada:
        raise PruebaAlterada('la prueba sellada cambió después de sellarla: su huella no es la del manifiesto')
    return dato


@dataclass
class Resultado:
    cohorte: str
    candidato: str
    metricas: dict[str, float] = field(default_factory=dict)
    es_base: bool = False
    puerta: bool = True
    motivo: str = ''


def informe(resultados: Sequence[Resultado], ruta: Path | str, *, plan, metrica: str,
            menor_es_mejor: bool = True) -> dict[str, Any]:
    """Publica todos los resultados, sin filtro previo, con la comparación contra la base de su cohorte."""
    cohortes = {c.nombre for c in plan.cohortes}
    ajenas = sorted({r.cohorte for r in resultados} - cohortes)
    if ajenas:
        raise ValueError(f'resultados de {cuenta(len(ajenas), "cohorte que no está en el plan", "cohortes que no están en el plan")}: no se publican')
    base = {}
    for r in resultados:
        if r.es_base:
            base.setdefault(r.cohorte, r.metricas.get(metrica))
    filas, negativos = [], 0
    for r in resultados:
        valor, referencia = r.metricas.get(metrica), base.get(r.cohorte)
        gana = None
        if not r.es_base and valor is not None and referencia is not None and math.isfinite(valor):
            gana = valor < referencia if menor_es_mejor else valor > referencia
        motivos = [r.motivo] if r.motivo else []
        if gana is False:
            motivos.append(f'peor que la base en {metrica}')
        negativo = not r.es_base and (gana is False or not r.puerta)
        negativos += negativo
        filas.append({'cohorte': r.cohorte, 'candidato': r.candidato, 'metricas': dict(r.metricas),
                      'es_base': r.es_base, 'puerta': r.puerta, 'gana_a_la_base': gana, 'negativo': negativo,
                      'motivo': '; '.join(motivos)})
    contenido = {'metrica': metrica, 'menor_es_mejor': menor_es_mejor, 'cohortes': sorted(cohortes),
                 'resultados': filas, 'negativos': negativos, 'avisos': list(plan.avisos)}
    publicar(Path(ruta), contenido)
    return contenido
