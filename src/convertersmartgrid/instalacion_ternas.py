"""Dos o más ternas subterráneas: su configuración de instalación y su capacidad (spec 084, RF-12 a RF-18).

Usuario, 2026-11-02, al explicar la capacidad de un cable con dos ternas supuestas juntas en una zanja: van
una por ducto, o en configuración de enterrado triangular o rectangular, y la capacidad es la del fabricante
para esa configuración. El tipo de DIgSILENT da la de un cable solo; doblarla por tener dos ternas juntas
daría una cargabilidad optimista sin aviso.

Aquí no hay factores de agrupamiento ni distancias: esos números son del fabricante y de la norma y se leen
de su texto, no se suponen. La tabla es del perfil de la empresa; sin ella se dice que falta (084:RF-15).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

#: Las tres instalaciones que admite la regla del usuario, con su nombre para el informe.
CONFIGURACIONES = {'ducto': 'una terna por ducto',
                   'triangular': 'en configuración de enterrado triangular',
                   'rectangular': 'en configuración de enterrado rectangular'}


def instalacion(*, tipo: str, ternas: int, cable: bool, perfil: Mapping[str, Any] | None,
                configuracion: str = '') -> dict[str, Any] | None:
    """La instalación de un tramo tras la obra; ``None`` si no aplica (084:RF-18).

    ``configuracion``: la de la obra; sin ella, la de ``planificacion.ternas_subterraneas`` del perfil.
    """
    if not cable or int(ternas) < 2:
        return None
    cfg = dict(((perfil or {}).get('planificacion') or {}).get('ternas_subterraneas') or {})
    elegida = str(configuracion or cfg.get('configuracion') or '').strip().lower()
    avisos: list[str] = []
    if elegida not in CONFIGURACIONES:
        if elegida:
            avisos.append(f'Configuración de ternas {elegida!r} desconocida: se deja sin definir (084:RF-13).')
        elegida = ''
        avisos.append(f'{int(ternas)} ternas subterráneas sin configuración definida: van una por ducto, o en '
                      'configuración de enterrado triangular o rectangular (084:RF-13).')
    capacidad = None
    if elegida:
        fila = (cfg.get('capacidad_a') or {}).get(tipo) or {}
        capacidad = float(fila[elegida]) if fila.get(elegida) else None
    if capacidad is None:
        avisos.append(f'Sin la capacidad del fabricante de {tipo} para esa configuración: la cargabilidad usa la del '
                      'tipo, sin confirmar para varias ternas (084:RF-15).')
    return {'ternas': int(ternas), 'tipo': tipo, 'configuracion': elegida or None, 'capacidad_a': capacidad,
            'avisos': avisos}


def capacidad_de_tramos(tramos: Iterable[Mapping[str, Any]], ternas: Mapping[str, Any] | None) -> dict[str, Any]:
    """``capacidad_terna_a`` por tramo de cable con dato, para que el oráculo no doble la del tipo (084:RF-16)."""
    perfil = {'planificacion': {'ternas_subterraneas': ternas or {}}}
    capacidades = {}
    for t in tramos:
        inst = instalacion(tipo=str(t.get('tipo') or ''), ternas=int(t.get('nlnum') or 1) + 1,
                           cable=bool(t.get('cable')), perfil=perfil)
        if inst and inst['capacidad_a']:
            capacidades[str(t['nombre'])] = inst['capacidad_a']
    return {'capacidad_terna_a': capacidades} if capacidades else {}


def factor_de_capacidad(inst: Mapping[str, Any] | None, inom_a: float | None) -> float | None:
    """El factor de reducción del tramo: la capacidad para esa configuración sobre la del tipo (084:RF-14)."""
    if not inst or not inst.get('capacidad_a') or not inom_a:
        return None
    return float(inst['capacidad_a']) / float(inom_a)


def describir(inst: Mapping[str, Any] | None) -> str:
    """La instalación en el informe: sin artículos ni distancias de norma (084:RF-17)."""
    if not inst:
        return ''
    n = inst['ternas']
    if inst.get('configuracion'):
        donde = f"{n} ternas subterráneas, {CONFIGURACIONES[inst['configuracion']]}"
    else:
        donde = f'{n} ternas subterráneas, con la configuración por definir (una terna por ducto, triangular o rectangular)'
    if inst.get('capacidad_a'):
        return f"{donde}, con {inst['capacidad_a']:g} A por terna según el fabricante para esa configuración."
    return f'{donde}; la capacidad del fabricante para esa configuración está sin confirmar.'
