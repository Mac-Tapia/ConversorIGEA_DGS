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
from .vnr_guia import (EQUIPO_POR_PREFIJO, RAICES_ANEXO2, ItemMetrado, ResultadoVnr, SedZonificable, Tramo,
                       TramoAdaptado, VnrGuiaError, adaptar_equipo, adaptar_red_bt, adaptar_red_mt, adaptar_sed,
                       calcular_vnr, codigo_de_equipo, codigo_de_sed, items_de_red, kva_adaptado, porciones_por_zona,
                       zonificar)

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
    equipos: list[dict] = field(default_factory=list)


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
    # 108:RF-23: VNR-GIS deja la baja tensión aparte (``sections_bt``, por SED): entra igual que la MT, con su SED.
    for s in [*modelo.sections, *getattr(modelo, 'sections_bt', [])]:
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
                                             inst.subterranea, zona, corrosivo(x, y),
                                             kv=getattr(s, 'nominal_kv', None),
                                             fases=inst.conductores if inst.nivel == 'BT' else 3,
                                             sed=getattr(s, 'sed_id', '') or s.feeder_id),
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
    equipos = _equipos(modelo, sector, registro, anexo2, items, huecos, fecha)
    resultado = calcular_vnr(items, tabla_costos, sector_sicodi, registro, fecha=fecha)
    return EstudioVnr(z_mt.resumen(), z_bt.resumen(), adaptados_mt, adaptados_bt, seds, resultado, huecos, equipos)


def _equipos(modelo, sector: str, registro: RegistroNormativo, anexo2: Mapping, items: list[ItemMetrado],
             huecos: list[str], fecha: str | None) -> list[dict]:
    """108:RF-23 — los equipos de protección y seccionamiento y los del componente C4 (bancos, reguladores y
    pararrayos), por su prefijo del Anexo 2: las maniobras del modelo, los bancos y los reguladores, y los que el lector
    no modela para el flujo (``equipos_no_modelados``: seccionadores cerrados y pararrayos). La Guía adapta los de
    EQUIPO_POR_PREFIJO; el resto se conserva. Uno por partida y tensión, con su cantidad."""
    tramos = {s.section_id: s for s in modelo.sections}
    tensiones = [s.nominal_kv for s in modelo.sections if s.nominal_kv and s.nominal_kv >= 1.0]  # la de la MT
    kv_red = max(set(tensiones), key=tensiones.count) if tensiones else None
    cuenta: dict[tuple[str, float | None, bool], int] = {}
    for w in modelo.switches:
        tramo = tramos.get(w.section_id)
        sub = bool(tramo and tramo.overhead is False)
        clave = ((w.kind or ('SL' if w.sectionalizer else '')).upper(), (tramo.nominal_kv if tramo else None) or kv_red, sub)
        cuenta[clave] = cuenta.get(clave, 0) + 1
    for prefijo, lista in (('BC', getattr(modelo, 'capacitors', [])), ('BR', getattr(modelo, 'regulators', []))):
        if lista:
            cuenta[(prefijo, kv_red, False)] = cuenta.get((prefijo, kv_red, False), 0) + len(lista)
    for prefijo, n in (getattr(modelo, 'metadata', {}) or {}).get('equipos_no_modelados', {}).items():
        cuenta[(str(prefijo).upper(), kv_red, False)] = cuenta.get((str(prefijo).upper(), kv_red, False), 0) + int(n)
    salida, notas = [], set()
    for (prefijo, kv, sub), n in sorted(cuenta.items(), key=lambda x: (x[0][0], x[0][1] or 0, x[0][2])):
        if not prefijo:
            huecos.append(f'{n} equipo(s) de maniobra sin tipo en VNR-GIS: no se valorizan')
            continue
        adaptado, cita = '', ''
        if prefijo in EQUIPO_POR_PREFIJO:
            try:
                adaptado, cita = adaptar_equipo(EQUIPO_POR_PREFIJO[prefijo], sub, sector, registro, fecha=fecha)
            except VnrGuiaError as exc:
                huecos.append(f'{n} equipo(s) {prefijo}: {exc}')
                continue
        try:
            codigo, nota = codigo_de_equipo(anexo2, prefijo, kv, adaptado)
        except VnrGuiaError as exc:
            huecos.append(f'{n} equipo(s) {prefijo}: {exc}')
            continue
        letra = letra_de_tension(anexo2, kv) if kv else None
        if letra is None:
            huecos.append(f'{n} equipo(s) {prefijo}: tensión {kv} kV sin código en la Tabla 9 del Anexo 3; no se valoriza')
            continue
        notas.add(nota)
        items.append(ItemMetrado(codigo, n, letra, 'X' if sub else POSTES[sector], f'{n} equipo(s) {prefijo}'))
        salida.append({'prefijo': prefijo, 'cantidad': n, 'kv': kv, 'subterraneo': sub, 'adaptado': adaptado,
                       'codigo': codigo, 'regla': cita})
    huecos.extend(sorted(notas))
    return salida
