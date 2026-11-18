"""F-123, mapa de densidad de carga del área (107:RF-9; tarjeta PIT-F123).

Los años salen de la nota (2) de la plantilla transcrita («Se presentan los mapas de densidad correspondientes a los
años: …»), no del código. Para cada año:

- la demanda de cada SED (su punto UTM y su kW del año 0) crece con el factor de su sistema eléctrico, que es el
  cociente de la potencia no coincidente regulatoria del año entre la del año 0 (F-110 de la 3c); los usuarios libres y
  las demandas incorporadas (F-116) entran como cargas concentradas en su punto. Es una deducción y así se anota: el
  estudio no proyecta SED por SED;
- la densidad por cuadrícula UTM del lado pedido (art. 7.9 a 7.11) y su zona y color de la Tabla N.º 2 salen de
  ``pide.cuadriculas`` y ``pide.zona_de_densidad``, los mismos de los mapas del PIDE;
- se dibujan el plano (PNG, que va a la hoja del formato), el DXF compatible con AutoCAD (una capa por zona, nota 1) y
  la base de datos de sustento (CSV, una fila por cuadrícula).

Sin SED con punto, el mapa del año sale vacío con su aviso. Un año por hoja: el primero en «F-123» y cada uno de los
demás en una copia de la hoja, que el libro de la entrega tiene que crear (``hojas_a_copiar``).
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ...aplicacion.pide import RANGOS_DENSIDAD, cuadriculas
from ...dominio.registro_normativo import RegistroError, RegistroNormativo
from ...dominio.pit import PitError

__all__ = ['DEDUCIDA', 'anios_del_formato', 'factores_por_sistema', 'mapas_f123', 'resultado_f123']

DEDUCIDA = ('demanda de cada SED crecida con el factor regulatorio de su sistema (F-110 del año / F-110 del año 0): '
            'deducida, el estudio no proyecta SED por SED')
#: Color de la Tabla N.º 2 → color del dibujo (RGB) y color AutoCAD (índice ACI).
COLORES = {'Rojo': ('#d62728', 1), 'Anaranjado': ('#ff7f0e', 30), 'Azul': ('#1f77b4', 5), 'Verde': ('#2ca02c', 3),
           'Amarillo': ('#ffdd57', 2)}


def anios_del_formato(registro: RegistroNormativo, fecha: str | None = None) -> list[int]:
    """Los años de los mapas, de la nota (2) de la plantilla del F-123."""
    try:
        filas = registro.regla('pit.formato.F-123', fecha).regla.valor['filas']
    except (RegistroError, KeyError, TypeError) as exc:
        raise PitError(f'F-123: su plantilla no está transcrita en el registro ({exc})') from exc
    nota = next((str(c) for f in filas for c in f['celdas'].values() if 'mapas de densidad' in str(c)), '')
    lista = nota.split('años', 1)[-1].replace('“', '').replace('”', '').replace('"', '')
    anios = [int(x) for x in re.findall(r'\d+', lista)]
    if not anios:
        raise PitError('F-123: la nota de la plantilla no dice de qué años son los mapas')
    return anios


def factores_por_sistema(cadena: Mapping[str, Any]) -> dict[str, list[float | None]]:
    """Por sistema eléctrico, la potencia no coincidente regulatoria de cada año entre la del año 0 (F-110)."""
    sumas: dict[str, list[float | None]] = {}
    for f in cadena['filas']['F-110']:
        serie = f.get('potencia_mw') or []
        previa = sumas.get(f['sistema'])
        sumas[f['sistema']] = list(serie) if previa is None else [
            None if a is None or b is None else a + b for a, b in zip(previa, serie)]
    return {s: [None if v is None or not serie[0] else v / serie[0] for v in serie] for s, serie in sumas.items()}


def _dibujar(celdas: Mapping[tuple[int, int], Mapping[str, Any]], lado: int, titulo: str, png: Path) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    fig, ax = plt.subplots(figsize=(8, 8), dpi=110)
    for (x, y), c in celdas.items():
        ax.add_patch(Rectangle((x, y), lado, lado, facecolor=COLORES[c['color']][0], edgecolor='#555555', linewidth=0.3))
    if celdas:
        xs, ys = [k[0] for k in celdas], [k[1] for k in celdas]
        ax.set_xlim(min(xs) - lado, max(xs) + 2 * lado)
        ax.set_ylim(min(ys) - lado, max(ys) + 2 * lado)
    ax.set_aspect('equal')
    ax.set_title(titulo, fontsize=10)
    ax.set_xlabel('Este (m)')
    ax.set_ylabel('Norte (m)')
    ax.legend(handles=[Patch(facecolor=COLORES[color][0], label=f'{zona} (≥ {minimo} MW/km²)')
                       for zona, minimo, color in RANGOS_DENSIDAD], loc='upper right', fontsize=7)
    fig.savefig(png, bbox_inches='tight')
    plt.close(fig)


def _dxf(celdas: Mapping[tuple[int, int], Mapping[str, Any]], lado: int, dxf: Path) -> None:
    import ezdxf

    doc = ezdxf.new('R2010')
    for zona, _minimo, color in RANGOS_DENSIDAD:
        doc.layers.add(f'DENSIDAD_{zona.upper().replace(" ", "_")}', color=COLORES[color][1])
    msp = doc.modelspace()
    for (x, y), c in celdas.items():
        capa = f'DENSIDAD_{c["zona"].upper().replace(" ", "_")}'
        msp.add_solid([(x, y), (x + lado, y), (x, y + lado), (x + lado, y + lado)], dxfattribs={'layer': capa})
        msp.add_text(f'{c["densidad_mw_km2"]:.2f}', dxfattribs={'layer': capa, 'height': lado / 8,
                                                                 'insert': (x + lado / 10, y + lado / 2)})
    doc.saveas(dxf)


def mapas_f123(registro: RegistroNormativo, seds: Sequence[Mapping[str, Any]],
               factores: Mapping[str, Sequence[float | None]], carpeta: Path | str, *,
               usuarios: Sequence[Mapping[str, Any]] = (), lado_m: int = 1000, area: str = '',
               fecha: str | None = None) -> dict[str, Any]:
    """Los mapas de los años del formato. ``seds``: cada una con ``este``, ``norte``, ``kw`` (año 0) y ``sistema``;
    ``usuarios``: ``este``, ``norte`` y ``potencia_mw`` (serie por año, F-116)."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    salida: dict[str, Any] = {'anios': {}, 'avisos': [], 'lado_m': lado_m, 'calculo': DEDUCIDA}
    con_punto = [s for s in seds if isinstance(s.get('este'), (int, float)) and isinstance(s.get('norte'), (int, float))]
    if len(con_punto) < len(seds):
        salida['avisos'].append(f'{len(seds) - len(con_punto)} SED sin punto UTM: no entran en el mapa')
    if not con_punto:
        salida['avisos'].append('ninguna SED con punto UTM: los mapas del F-123 salen vacíos')
    for anio in anios_del_formato(registro, fecha):
        puntos, sin_factor = [], set()
        for s in con_punto:
            serie = factores.get(s.get('sistema')) or []
            f = serie[anio] if anio < len(serie) else None
            if f is None:
                sin_factor.add(str(s.get('sistema')))
                continue
            puntos.append((float(s['este']), float(s['norte']), float(s['kw']) * f, False))
        for u in usuarios:
            serie = u.get('potencia_mw') or []
            mw = serie[anio] if anio < len(serie) else None
            if isinstance(u.get('este'), (int, float)) and isinstance(u.get('norte'), (int, float)) and mw:
                puntos.append((float(u['este']), float(u['norte']), mw * 1000, True))
        if sin_factor:
            salida['avisos'].append(f'año {anio}: sin factor regulatorio del sistema {", ".join(sorted(sin_factor))}')
        celdas = cuadriculas(puntos, lado_m)
        base = carpeta / f'F-123_anio_{anio:02d}'
        _dibujar(celdas, lado_m, f'Mapa de densidad de carga · {area} · año {anio}', base.with_suffix('.png'))
        _dxf(celdas, lado_m, base.with_suffix('.dxf'))
        with base.with_suffix('.csv').open('w', encoding='utf-8', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['este', 'norte', 'lado_m', 'mw', 'mw_concentradas', 'densidad_mw_km2', 'zona'])
            for (x, y), c in sorted(celdas.items()):
                w.writerow([x, y, lado_m, round(c['mw'], 6), round(c['mw_concentradas'], 6),
                            round(c['densidad_mw_km2'], 6), c['zona']])
        salida['anios'][anio] = {'png': str(base.with_suffix('.png')), 'dxf': str(base.with_suffix('.dxf')),
                                 'csv': str(base.with_suffix('.csv')), 'cuadriculas': len(celdas),
                                 'zonas': dict(Counter(c['zona'] for c in celdas.values()))}
    return salida


def resultado_f123(mapas: Mapping[str, Any], area: str | None) -> dict[str, Any]:
    """Las celdas y las imágenes del F-123: una hoja por año (la primera «F-123», las demás sus copias)."""
    celdas, imagenes, copiar = [], [], []
    for k, (anio, m) in enumerate(sorted(mapas['anios'].items()), start=1):
        hoja = 'F-123' if k == 1 else f'F-123 ({k})'
        if k > 1:
            copiar.append({'de': 'F-123', 'a': hoja, 'anio': anio})
        traza = {'calculo': mapas['calculo'], 'lado_m': mapas['lado_m'], 'dxf': m['dxf'], 'csv': m['csv']}
        celdas += [{'id': f'{hoja}!area', 'cuadro': 'F-123', 'bloque': 'cabecera', 'fila': 0, 'campo': 'area',
                    'columna': 'AREA DE DEMANDA:', 'celda': f'{hoja}!B4', 'valor': area, 'traza': traza},
                   {'id': f'{hoja}!anio', 'cuadro': 'F-123', 'bloque': 'cabecera', 'fila': 0, 'campo': 'anio',
                    'columna': 'AÑO (2) :', 'celda': f'{hoja}!H4', 'valor': anio, 'traza': traza}]
        imagenes.append({'celda': f'{hoja}!A6', 'ruta': m['png']})
    resultado: dict[str, Any] = {'codigo': 'F-123', 'celdas': celdas, 'imagenes': imagenes, 'huecos': [],
                                 'filas_a_insertar': {}, 'insertar_en': [], 'grupos_a_insertar': {},
                                 'avisos': list(mapas['avisos'])}
    if copiar:
        resultado['hojas_a_copiar'] = copiar
    return resultado
