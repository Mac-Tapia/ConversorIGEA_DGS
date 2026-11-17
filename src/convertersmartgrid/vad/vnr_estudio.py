"""Estudio VNR de una empresa desde su inventario VNR-GIS (modelo canónico del módulo ``vnr``), con la Guía del VNR
(RCD 232-2017-OS/CD; spec 108, RF-21 a RF-25).

Cada tramo del inventario lleva en ``conductor_code`` su código VNR del Anexo 2 y la letra de tensión de la Tabla 9 del
Anexo 3 (p. ej. «AA05003D»): de la descripción del Anexo 2 salen su material, su sección y sus conductores. Las SED son
los transformadores del modelo, con la máxima demanda de las cargas de su nodo. El estudio zonifica (art. 22), reparte
cada tramo por las zonas que cruza, adapta (arts. 23 a 44), codifica y valoriza (art. 17.2). Lo que falta para una regla
(una SED sin demanda, un código que el Anexo 2 no tiene) queda como hueco nombrado: nunca se inventa.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ..registro_normativo import RegistroNormativo
from .vnr_guia import (RAICES_ANEXO2, ItemMetrado, ResultadoVnr, SedZonificable, Tramo, TramoAdaptado, VnrGuiaError,
                       adaptar_red_bt, adaptar_red_mt, adaptar_sed, calcular_vnr, codigo_de_sed, items_de_red,
                       kva_adaptado, porciones_por_zona, zonificar)

POSTES = {'urbano_alta': 'C', 'urbano_media_baja': 'C', 'urbano_rural': 'C', 'rural_ser': 'A'}  # Tabla 11: C/A
_FORMA = re.compile(r'(?<![\d,])(\d)(?:-1)?x(\d+(?:,\d+)?) mm2')


@dataclass(frozen=True)
class Instalacion:
    nivel: str
    subterranea: bool
    material: str
    seccion_mm2: float
    conductores: int


def instalacion_de_codigo(anexo2: Mapping, codigo: str) -> Instalacion:
    """Material, sección y conductores de un código VNR de red, por su descripción en el Anexo 2."""
    for c in anexo2['codigos']:
        if c['codigo'] != codigo:
            continue
        nivel = {'1': 'MT', '3': 'BT'}.get(c['grupo'].split()[0])
        if nivel is None:
            break
        for subterranea in (False, True):
            sub, raices = RAICES_ANEXO2[(nivel, subterranea)]
            if not c['subcomponente'].startswith(sub.strip()[:2]):
                continue
            for material, raiz in sorted(raices.items(), key=lambda kv: -len(kv[1])):
                m = _FORMA.search(c['descripcion'])
                if raiz in c['descripcion'] and m:
                    return Instalacion(nivel, subterranea, material, float(m.group(2).replace(',', '.')),
                                       int(m.group(1)))
        break
    raise VnrGuiaError(f'{codigo}: no es un código de red del Anexo 2 que el estudio sepa leer')


def letra_de_tension(anexo2: Mapping, kv: float | None, *, baja: bool = False) -> str | None:
    """La letra de la Tabla 9 del Anexo 3 para una tensión nominal en kV: MT por su valor (10 kV → D); BT por la tensión
    entre fases (0,22 → X, 0,38 → Y «380/220 V», 0,44 → Z «440/220 V»)."""
    if kv is None:
        return None
    for letra, texto in anexo2['tensiones'].items():
        valor = texto.split('/')[0].replace(',', '.').replace(' kV', '').replace(' V', '')
        en_kv = float(valor) / (1000.0 if texto.endswith(' V') else 1.0)
        if texto.endswith(' V') == baja and abs(en_kv - kv) < 1e-6 + 0.005 * kv:
            return letra
    return None


@dataclass
class EstudioVnr:
    zonas_mt: dict[str, int]
    zonas_bt: dict[str, int]
    adaptados_mt: list[TramoAdaptado]
    adaptados_bt: list[TramoAdaptado]
    seds: list[dict]
    resultado: ResultadoVnr
    huecos: list[str] = field(default_factory=list)


def estudio_vnr(modelo, *, sector: str, sector_sicodi: str, tabla_costos, registro: RegistroNormativo,
                anexo2: Mapping, anexo6: Mapping, corrosivo: Callable[[float, float], bool] | None = None,
                fecha: str | None = None) -> EstudioVnr:
    """El VNR adaptado de ``modelo`` (CanonicalModel). ``corrosivo(x, y)`` dice si un punto está en ambiente corrosivo
    (franja costera; ver ``vnr_guia.es_corrosivo``); sin él, todo es no corrosivo y queda dicho en los huecos."""
    huecos: list[str] = []
    if corrosivo is None:
        huecos.append('sin la franja costera del ambiente corrosivo: todos los tramos se adaptan como no corrosivos '
                      '(art. 22.1); dé la función de ambiente para una costa')
        corrosivo = lambda x, y: False  # noqa: E731
    nodos = {n.node_id: n for n in modelo.nodes}
    md_por_nodo: dict[str, float] = {}
    for c in modelo.loads:
        md_por_nodo[c.connection_node] = md_por_nodo.get(c.connection_node, 0.0) + float(c.kw or 0.0)
    seds_z, seds_info = [], []
    for t in modelo.transformers:
        n = nodos.get(t.connection_node)
        md = md_por_nodo.get(t.connection_node)
        if n is None or n.x is None or n.y is None:
            huecos.append(f'SED {t.transformer_id}: sin coordenadas; no entra en la zonificación')
            continue
        seds_z.append(SedZonificable(t.transformer_id, n.x, n.y, md or 0.0))
        seds_info.append((t, n, md))
    z_mt = zonificar(seds_z, registro, mapa='MT', fecha=fecha)
    z_bt = zonificar(seds_z, registro, mapa='BT', fecha=fecha)
    tramos = {'MT': [], 'BT': []}
    for s in modelo.sections:
        codigo, letra = (s.conductor_code[:-1], s.conductor_code[-1:]) if s.conductor_code else ('', '')
        try:
            inst = instalacion_de_codigo(anexo2, codigo)
        except VnrGuiaError as exc:
            huecos.append(f'tramo {s.section_id}: {exc}')
            continue
        puntos = [tuple(p) for p in (s.geometry or [])]
        zonas = z_mt if inst.nivel == 'MT' else z_bt
        partes = porciones_por_zona(puntos, zonas) if len(puntos) >= 2 else {'Baja': float(s.length_m or 0.0)}
        x, y = puntos[len(puntos) // 2] if puntos else (0.0, 0.0)
        for zona, largo in sorted(partes.items()):
            tramos[inst.nivel].append((Tramo(f'{s.section_id}/{zona}', inst.material, inst.seccion_mm2, largo,
                                             inst.subterranea, zona, corrosivo(x, y), kv=s.nominal_kv,
                                             fases=inst.conductores if inst.nivel == 'BT' else 3, sed=s.feeder_id),
                                       letra))
    adaptados_mt = adaptar_red_mt([t for t, _ in tramos['MT']], sector, registro, anexo6, fecha=fecha)
    adaptados_bt = adaptar_red_bt([t for t, _ in tramos['BT']], sector, registro, anexo6, fecha=fecha)
    items: list[ItemMetrado] = []
    for nivel, adaptados in (('MT', adaptados_mt), ('BT', adaptados_bt)):
        por_letra: dict[str, list[TramoAdaptado]] = {}
        for (_, letra), a in zip(tramos[nivel], adaptados, strict=True):
            por_letra.setdefault(letra or ('D' if nivel == 'MT' else 'X'), []).append(a)
        for letra, grupo in sorted(por_letra.items()):
            items += items_de_red(grupo, anexo2, nivel, letra, postes=POSTES[sector])
    seds = []
    for t, n, md in seds_info:
        if md is None or md <= 0:
            huecos.append(f'SED {t.transformer_id}: sin máxima demanda de sus cargas; su kVA adaptado no se calcula')
            continue
        kva = kva_adaptado(md, sector, registro, fecha=fecha)
        zona = z_mt.zona_en(n.x, n.y)
        fases = 1 if (n.phases and len(n.phases) == 1) else 3
        try:
            tipo, cita = adaptar_sed('Todas', kva, fases, zona, sector, registro, fecha=fecha)
            codigo, kva_cat = codigo_de_sed(anexo2, tipo, kva)
        except VnrGuiaError as exc:
            huecos.append(f'SED {t.transformer_id}: {exc}')
            continue
        letra, bt = letra_de_tension(anexo2, t.hv_kv), letra_de_tension(anexo2, t.lv_kv, baja=True)
        if letra is None or bt is None:
            huecos.append(f'SED {t.transformer_id}: tensión {t.hv_kv} kV / {t.lv_kv} kV sin código en la Tabla 9 del '
                          'Anexo 3; no se valoriza')
            continue
        seds.append({'sed': t.transformer_id, 'md_kw': md, 'kva_adaptado': kva, 'zona': zona, 'tipo': tipo,
                     'codigo': codigo, 'kva_catalogo': kva_cat, 'regla': cita})
        items.append(ItemMetrado(codigo, 1, letra, bt, f'SED {t.transformer_id}'))
    resultado = calcular_vnr(items, tabla_costos, sector_sicodi, registro, fecha=fecha)
    return EstudioVnr(z_mt.resumen(), z_bt.resumen(), adaptados_mt, adaptados_bt, seds, resultado, huecos)
