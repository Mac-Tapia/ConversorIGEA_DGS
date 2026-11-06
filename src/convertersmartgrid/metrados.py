"""Metrados de una red, desde su propio modelo: de ahí sale el costo, no de un largo supuesto (072:RF-15).

`pide_economia.propuesta_pide` valora hoy una obra por km con 1 km supuesto y lo avisa. El metrado
real ya está en el modelo: cada tramo tiene su código, su largo y si es aéreo. Un tramo sin código
no se reparte entre los demás: se nombra, para que el costo no lo oculte.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .costos_fuentes import TablaCostos, exigir_ambito, partir_codigo_vnr


def metrados_de_lineas(lineas: Iterable[Any]) -> dict[str, Any]:
    """Tramos y km por código, y lo que no se puede atribuir a ninguno (072:RF-15)."""
    por_codigo: dict[str, dict[str, float]] = {}
    sin_codigo: list[str] = []
    tramos = 0
    km = km_sin_codigo = 0.0
    for linea in lineas:
        largo = float(linea.length_m) / 1000.0
        tramos += 1
        km += largo
        codigo = str(linea.source_type_code or '').strip()
        if not codigo:
            sin_codigo.append(str(linea.section_id))
            km_sin_codigo += largo
            continue
        fila = por_codigo.setdefault(codigo, {'tramos': 0, 'km': 0.0, 'km_aereo': 0.0, 'km_subterraneo': 0.0})
        fila['tramos'] += 1
        fila['km'] += largo
        fila['km_aereo' if linea.overhead else 'km_subterraneo'] += largo
    return {'tramos': tramos, 'km': km, 'por_codigo': dict(sorted(por_codigo.items())),
            'sin_codigo': sin_codigo, 'km_sin_codigo': km_sin_codigo}


def valorar_metrados(por_codigo: Mapping[str, Mapping[str, float]], tabla: TablaCostos, *, sector: str,
                     estructura: str) -> dict[str, Any]:
    """Metrado × costo de red; lo que no cruza queda fuera del total y nombrado (072:RF-7, RF-15).

    Solo la familia de redes va por km: Osinergmin expresa esos costos en USD/km (informe de
    observaciones al VAD de Electro Oriente, 2023). Otra familia no se multiplica por un largo.
    """
    # Los tramos de la red de distribución van con el SICODI; un módulo de transmisión que cruzara
    # por código daría un costo de otro ámbito sin que nada lo dijera (072:RF-6).
    exigir_ambito(tabla, 'distribucion')
    valorados, sin_costo = [], []
    for codigo_red, fila in por_codigo.items():
        codigo, tension = partir_codigo_vnr(codigo_red)
        costo = tabla.buscar(codigo, tension, estructura, sector)
        # La estructura pedida es la de la red aérea; un tramo solo subterráneo usa la que tiene su código.
        if costo is None and not fila.get('km_aereo'):
            unica = tabla.estructura_unica(codigo, tension, sector)
            costo = tabla.buscar(codigo, tension, unica, sector) if unica else None
        if costo is None:
            sin_costo.append({'codigo': codigo_red, 'km': fila['km'],
                              'motivo': tabla.motivo_sin_costo(codigo, tension, estructura, sector)})
        elif not costo.familia.upper().startswith('RED'):
            sin_costo.append({'codigo': codigo_red, 'km': fila['km'],
                              'motivo': f'{codigo_red} es de la familia «{costo.familia}», que no se valora por km'})
        else:
            valorados.append({'codigo': codigo_red, 'km': fila['km'], 'costo_por_km': costo.total,
                              'costo': fila['km'] * costo.total, 'nombre': costo.nombre})
    return {'moneda': tabla.fuente.moneda, 'resolucion': tabla.fuente.resolucion, 'sector': sector,
            'estructura': estructura, 'total': sum(x['costo'] for x in valorados),
            'km_valorados': sum(x['km'] for x in valorados), 'km_sin_costo': sum(x['km'] for x in sin_costo),
            'valorados': valorados, 'sin_costo': sin_costo}
